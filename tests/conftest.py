import os
import sys
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "sqlite:///./test.db",
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"
os.environ["YOUTUBE_API_KEY"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["LLM_PROVIDER"] = "groq"
os.environ["LLM_MODEL"] = "llama-3.3-70b-versatile"

# Mock heavy dependencies before importing app
mock_search_service = MagicMock()
mock_search_service.search.return_value = []
mock_search_service.get_collection.return_value = MagicMock()

mock_llm_service = MagicMock()
mock_llm_service.answer.return_value = "Resposta gerada pela IA [1]"

# Mock modules that have heavy dependencies
sys.modules['app.services.SemanticSearchService'] = MagicMock(
    SemanticSearchService=lambda: mock_search_service
)
class _FakeLLMRateLimitError(Exception):
    def __init__(self, message="rate limit", retry_after_seconds=300):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class _FakeLLMTimeoutError(Exception):
    pass


class _FakeLLMConnectionError(Exception):
    pass


sys.modules['app.services.LLMService'] = MagicMock(
    LLMService=MagicMock(),
    LLMRateLimitError=_FakeLLMRateLimitError,
    LLMTimeoutError=_FakeLLMTimeoutError,
    LLMConnectionError=_FakeLLMConnectionError
)
sys.modules['app.celery.ai_tasks'] = MagicMock()
sys.modules['app.celery.tasks'] = MagicMock()
sys.modules['app.celery.celery_app'] = MagicMock(celery=MagicMock())

from app.database import Base, get_db
from app.main import app
from app.models.UserModel import User, RevokedToken
from app.models.VideoModel import Video, Comment
from app.models.VideoInsightModel import VideoInsight
from app.core.security import hash_password, create_token_pair


TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False} if TEST_DATABASE_URL.startswith("sqlite") else {})

# SQLite não aplica foreign keys por padrão; sem isso os testes não pegam
# violações de FK (ex: DELETE de vídeo com comentários).
if TEST_DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    if os.path.exists("./test.db"):
        os.remove("./test.db")


@pytest.fixture(scope="function")
def db_session():
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db_session, request):
    def override_get_db():
        yield db_session
    
    def override_get_search_service():
        return mock_search_service

    def override_get_llm_service():
        return mock_llm_service

    # Estado dos mocks não deve vazar entre testes
    mock_search_service.reset_mock()
    mock_search_service.search.return_value = []
    mock_llm_service.reset_mock()
    mock_llm_service.answer.return_value = "Resposta gerada pela IA [1]"
    mock_llm_service.answer.side_effect = None
    
    # Reset the original limiter's storage (used by route decorators)
    from app.core.rate_limiter import limiter as original_limiter
    if hasattr(original_limiter, 'reset'):
        original_limiter.reset()
    elif hasattr(original_limiter._storage, 'reset'):
        original_limiter._storage.reset()
    
    app.dependency_overrides[get_db] = override_get_db
    from app.dependencies import get_search_service, get_llm_service
    app.dependency_overrides[get_search_service] = override_get_search_service
    app.dependency_overrides[get_llm_service] = override_get_llm_service
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session):
    user = User(
        email="test@example.com",
        hashed_password=hash_password("senha123"),
        role="user",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session):
    user = User(
        email="admin@example.com",
        hashed_password=hash_password("admin123"),
        role="admin",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user):
    token_pair = create_token_pair(test_user.id, "user")
    return {"Authorization": f"Bearer {token_pair.access_token}"}


@pytest.fixture
def admin_auth_headers(admin_user):
    token_pair = create_token_pair(admin_user.id, "admin")
    return {"Authorization": f"Bearer {token_pair.access_token}"}


@pytest.fixture
def test_video(db_session, test_user):
    video = Video(
        youtube_id="test_video_id",
        titulo="Test Video",
        user_id=test_user.id
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video


@pytest.fixture
def other_user(db_session):
    user = User(
        email="other@example.com",
        hashed_password=hash_password("senha123"),
        role="user",
        is_active=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def other_user_video(db_session, other_user):
    video = Video(
        youtube_id="other_video_id",
        titulo="Other User Video",
        user_id=other_user.id
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video