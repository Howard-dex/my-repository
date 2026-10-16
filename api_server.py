from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
import uuid

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Boolean, DateTime, Integer, String, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


# ==========================================
# 1. 数据库配置与 ORM 模型层 (database & models)
# ==========================================

SQLALCHEMY_DATABASE_URL = "sqlite:///./dispatch.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}  # SQLite 多线程支持
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class OrderStatus(str, Enum):
    PENDING = "PENDING"       # 待派单
    ASSIGNED = "ASSIGNED"     # 已派单/处理中
    COMPLETED = "COMPLETED"   # 已办结
    FAILED = "FAILED"         # 自动派单失败(滞留)


class WorkerORM(Base):
    __tablename__ = "workers"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    skills: Mapped[List[str]] = mapped_column(JSON, default=list)  # 以 JSON 数组持久化技能标签
    max_load: Mapped[int] = mapped_column(Integer, default=3)
    current_load: Mapped[int] = mapped_column(Integer, default=0)
    is_online: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def is_available(self) -> bool:
        return self.is_online and self.current_load < self.max_load

    @property
    def load_ratio(self) -> float:
        return self.current_load / self.max_load if self.max_load > 0 else 1.0


class OrderORM(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(16), primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    required_skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    priority: Mapped[int] = mapped_column(Integer, default=1, index=True)  # 1:普通, 2:紧急, 3:特急
    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.PENDING.value, index=True)
    assigned_worker_id: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    assigned_mode: Mapped[str] = mapped_column(String(64), default="-")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


# ==========================================
# 2. Pydantic 数据校验与序列化层 (schemas)
# ==========================================

class WorkerCreate(BaseModel):
    name: str = Field(..., example="张师傅", description="接单员姓名")
    skills: Set[str] = Field(default_factory=set, example=["水电", "硬件维修"])
    max_load: int = Field(default=3, ge=1, le=50, description="最大同时接单上限")
    is_online: bool = Field(default=True)


class WorkerStatusUpdate(BaseModel):
    is_online: Optional[bool] = None
    max_load: Optional[int] = Field(default=None, ge=1, le=50)
    skills: Optional[Set[str]] = None


class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    skills: List[str]
    max_load: int
    current_load: int
    is_online: bool
    is_available: bool
    load_ratio: float


class OrderCreate(BaseModel):
    title: str = Field(..., example="5楼机房核心交换机断网抢修")
    required_skills: Set[str] = Field(default_factory=set, example=["网络", "VIP专属"])
    priority: int = Field(default=1, ge=1, le=99, description="优先级：数字越大越优先")
    auto_dispatch: bool = Field(default=True, description="创建后是否立即触发自动派单")
    strategy: str = Field(default="least_loaded", description="可选: least_loaded, load_ratio, round_robin")


class ManualAssignRequest(BaseModel):
    worker_id: str = Field(..., example="W001", description="目标接单员ID")
    force: bool = Field(default=False, description="是否忽略离线/满载/技能不符限制强制指派")


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    required_skills: List[str]
    priority: int
    status: str
    assigned_worker_id: Optional[str]
    assigned_mode: str
    created_at: datetime


# ==========================================
# 3. 派单策略引擎层 (strategies)
# ==========================================

class DispatchStrategy(ABC):
    @abstractmethod
    def select_worker(self, order: OrderORM, workers: List[WorkerORM]) -> Optional[WorkerORM]:
        pass

    def filter_qualified(self, order: OrderORM, workers: List[WorkerORM]) -> List[WorkerORM]:
        req_skills = set(order.required_skills or [])
        return [
            w for w in workers
            if w.is_available and req_skills.issubset(set(w.skills or []))
        ]


class LeastLoadedStrategy(DispatchStrategy):
    def select_worker(self, order: OrderORM, workers: List[WorkerORM]) -> Optional[WorkerORM]:
        qualified = self.filter_qualified(order, workers)
        return min(qualified, key=lambda w: w.current_load) if qualified else None


class LoadRatioStrategy(DispatchStrategy):
    def select_worker(self, order: OrderORM, workers: List[WorkerORM]) -> Optional[WorkerORM]:
        qualified = self.filter_qualified(order, workers)
        return min(qualified, key=lambda w: w.load_ratio) if qualified else None


class RoundRobinStrategy(DispatchStrategy):
    def __init__(self):
        self._cursor = -1

    def select_worker(self, order: OrderORM, workers: List[WorkerORM]) -> Optional[WorkerORM]:
        qualified = self.filter_qualified(order, workers)
        if not qualified:
            return None
        self._cursor = (self._cursor + 1) % len(qualified)
        return qualified[self._cursor]


STRATEGY_REGISTRY: Dict[str, DispatchStrategy] = {
    "least_loaded": LeastLoadedStrategy(),
    "load_ratio": LoadRatioStrategy(),
    "round_robin": RoundRobinStrategy(),
}


# ==========================================
# 4. 核心业务与事务调度服务层 (service)
# ==========================================

class DispatchService:
    @staticmethod
    def auto_dispatch_order(db: Session, order: OrderORM, strategy_name: str = "least_loaded") -> bool:
        strategy = STRATEGY_REGISTRY.get(strategy_name)
        if not strategy:
            raise HTTPException(status_code=400, detail=f"未知的策略名称: {strategy_name}")

        workers = db.query(WorkerORM).filter(WorkerORM.is_online == True).all()
        selected = strategy.select_worker(order, workers)

        if selected:
            selected.current_load += 1
            order.assigned_worker_id = selected.id
            order.status = OrderStatus.ASSIGNED.value
            order.assigned_mode = f"AUTO({strategy_name})"
            db.commit()
            db.refresh(order)
            return True
        else:
            order.status = OrderStatus.FAILED.value
            db.commit()
            db.refresh(order)
            return False

    @staticmethod
    def manual_dispatch_order(db: Session, order: OrderORM, worker: WorkerORM, force: bool = False) -> OrderORM:
        if order.status == OrderStatus.COMPLETED.value:
            raise HTTPException(status_code=400, detail="已办结工单无法重新派发")

        # 校验人员资格（除非开启 force 强制指派）
        if not force:
            if not worker.is_online:
                raise HTTPException(status_code=400, detail=f"接单员 {worker.name} 当前离线（可设置 force=true 强制指派）")
            if worker.current_load >= worker.max_load:
                raise HTTPException(status_code=400, detail=f"接单员 {worker.name} 已满载（可设置 force=true 强制指派）")
            missing_skills = set(order.required_skills) - set(worker.skills)
            if missing_skills:
                raise HTTPException(
                    status_code=400,
                    detail=f"接单员缺少所需技能: {list(missing_skills)}（可设置 force=true 强制指派）"
                )

        # 如果该工单此前已指派给其他人，先释放原接单员负载（支持转派）
        if order.status == OrderStatus.ASSIGNED.value and order.assigned_worker_id:
            prev_worker = db.query(WorkerORM).filter(WorkerORM.id == order.assigned_worker_id).first()
            if prev_worker and prev_worker.current_load > 0:
                prev_worker.current_load -= 1

        worker.current_load += 1
        order.assigned_worker_id = worker.id
        order.status = OrderStatus.ASSIGNED.value
        order.assigned_mode = "MANUAL(FORCE)" if force else "MANUAL"
        db.commit()
        db.refresh(order)
        return order


# ==========================================
# 5. FastAPI 生命周期与路由层 (main & routers)
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时自动建表并注入初始测试数据（若库为空）
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(WorkerORM).count() == 0:
            seed_workers = [
                WorkerORM(id="W001", name="张师傅", skills=["水电", "硬件维修"], max_load=3, is_online=True),
                WorkerORM(id="W002", name="李工", skills=["网络", "VIP专属", "软件调试"], max_load=4, is_online=True),
                WorkerORM(id="W003", name="王哥", skills=["水电", "高空作业"], max_load=2, is_online=False),
            ]
            db.add_all(seed_workers)
            db.commit()
    yield


app = FastAPI(
    title="智能派单调度系统 API",
    description="基于 FastAPI + SQLite 的持久化派单服务，支持多策略自动派单、人工强制指派及结单自动补位。",
    version="1.0.0",
    lifespan=lifespan
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------- 接单员管理接口 ----------------

@app.post("/workers", response_model=WorkerResponse, tags=["1. 接单员管理 (Workers)"])
def create_worker(payload: WorkerCreate, db: Session = Depends(get_db)):
    """注册新接单员"""
    worker_id = f"W{str(uuid.uuid4())[:4].upper()}"
    worker = WorkerORM(
        id=worker_id,
        name=payload.name,
        skills=list(payload.skills),
        max_load=payload.max_load,
        is_online=payload.is_online
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker


@app.get("/workers", response_model=List[WorkerResponse], tags=["1. 接单员管理 (Workers)"])
def list_workers(only_online: bool = False, db: Session = Depends(get_db)):
    """查询所有接单员及实时负载状态"""
    query = db.query(WorkerORM)
    if only_online:
        query = query.filter(WorkerORM.is_online == True)
    return query.all()


@app.patch("/workers/{worker_id}", response_model=WorkerResponse, tags=["1. 接单员管理 (Workers)"])
def update_worker_status(worker_id: str, payload: WorkerStatusUpdate, db: Session = Depends(get_db)):
    """修改接单员状态（上线/下线、扩容最大接单数、更新技能）"""
    worker = db.query(WorkerORM).filter(WorkerORM.id == worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="接单员不存在")

    if payload.is_online is not None:
        worker.is_online = payload.is_online
    if payload.max_load is not None:
        worker.max_load = payload.max_load
    if payload.skills is not None:
        worker.skills = list(payload.skills)

    db.commit()
    db.refresh(worker)
    return worker


# ---------------- 工单与派单调度接口 ----------------

@app.post("/orders", response_model=OrderResponse, tags=["2. 工单与派单调度 (Orders)"])
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    """创建新工单（可通过 auto_dispatch 控制是否立即自动派单）"""
    order_id = f"ORD-{str(uuid.uuid4())[:6].upper()}"
    new_order = OrderORM(
        id=order_id,
        title=payload.title,
        required_skills=list(payload.required_skills),
        priority=payload.priority,
        status=OrderStatus.PENDING.value
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    if payload.auto_dispatch:
        DispatchService.auto_dispatch_order(db, new_order, strategy_name=payload.strategy)

    return new_order


@app.get("/orders", response_model=List[OrderResponse], tags=["2. 工单与派单调度 (Orders)"])
def list_orders(
    status: Optional[OrderStatus] = Query(None, description="按状态过滤"),
    db: Session = Depends(get_db)
):
    """查询工单列表（默认按优先级降序、创建时间升序排列）"""
    query = db.query(OrderORM)
    if status:
        query = query.filter(OrderORM.status == status.value)
    return query.order_by(OrderORM.priority.desc(), OrderORM.created_at.asc()).all()


@app.post("/orders/{order_id}/dispatch/auto", response_model=OrderResponse, tags=["2. 工单与派单调度 (Orders)"])
def trigger_auto_dispatch(
    order_id: str,
    strategy: str = Query("least_loaded", description="策略: least_loaded / load_ratio / round_robin"),
    db: Session = Depends(get_db)
):
    """对单个待处理/滞留工单触发自动派单"""
    order = db.query(OrderORM).filter(OrderORM.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")
    if order.status in (OrderStatus.ASSIGNED.value, OrderStatus.COMPLETED.value):
        raise HTTPException(status_code=400, detail=f"当前工单状态为 {order.status}，无需重复自动派单")

    DispatchService.auto_dispatch_order(db, order, strategy_name=strategy)
    return order


@app.post("/orders/{order_id}/dispatch/manual", response_model=OrderResponse, tags=["2. 工单与派单调度 (Orders)"])
def trigger_manual_dispatch(
    order_id: str,
    payload: ManualAssignRequest,
    db: Session = Depends(get_db)
):
    """人工点选指定人员派单（支持在途工单转派、支持 force=True 强制指派）"""
    order = db.query(OrderORM).filter(OrderORM.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="工单不存在")

    worker = db.query(WorkerORM).filter(WorkerORM.id == payload.worker_id).first()
    if not worker:
        raise HTTPException(status_code=404, detail="目标接单员不存在")

    return DispatchService.manual_dispatch_order(db, order, worker, force=payload.force)


@app.post("/orders/{order_id}/complete", response_model=Dict, tags=["2. 工单与派单调度 (Orders)"])
def complete_order(order_id: str, auto_assign_next: bool = True, db: Session = Depends(get_db)):
    """
    确认结单并释放人员负载。
    若开启 auto_assign_next=True，释放名额后会自动从滞留池中按优先级捞取匹配工单补位派发。
    """
    order = db.query(OrderORM).filter(OrderORM.id == order_id).first()
    if not order or order.status != OrderStatus.ASSIGNED.value:
        raise HTTPException(status_code=400, detail="工单不存在或当前并非处理中状态")

    worker = db.query(WorkerORM).filter(WorkerORM.id == order.assigned_worker_id).first()
    if worker and worker.current_load > 0:
        worker.current_load -= 1

    order.status = OrderStatus.COMPLETED.value
    db.commit()

    # 结单后自动捞取积压单补位
    reassigned_order_id = None
    if auto_assign_next:
        pending_list = (
            db.query(OrderORM)
            .filter(OrderORM.status.in_([OrderStatus.PENDING.value, OrderStatus.FAILED.value]))
            .order_by(OrderORM.priority.desc(), OrderORM.created_at.asc())
            .all()
        )
        for pending_order in pending_list:
            if DispatchService.auto_dispatch_order(db, pending_order):
                reassigned_order_id = pending_order.id
                break

    return {
        "completed_order_id": order.id,
        "released_worker": worker.name if worker else None,
        "auto_reassigned_pending_order": reassigned_order_id
    }