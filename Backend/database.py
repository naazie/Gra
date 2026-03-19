# import os
# from sqlalchemy import create_engine, Column, Integer, String, DateTime
# from sqlalchemy.orm import declarative_base, sessionmaker
# import bcrypt
# from datetime import datetime
# from jose import jwt
# from dotenv import load_dotenv

# load_dotenv()

# # ================= PRODUCTION CONFIG =================

# _user     = os.getenv("POSTGRES_USER",     "your_postgres_user")
# _password = os.getenv("POSTGRES_PASSWORD", "your_postgres_password")
# _host     = os.getenv("POSTGRES_HOST",     "127.0.0.1")
# _port     = os.getenv("POSTGRES_PORT",     "5433")
# _db       = os.getenv("POSTGRES_DB",       "gm_auth")

# URL        = f"postgresql+psycopg://{_user}:{_password}@{_host}:{_port}/{_db}"
# SECRET_KEY = os.getenv("SECRET_KEY", "GRAPH_MIND_ULTIMATE_SECRET_KEY")
# ALGORITHM  = os.getenv("ALGORITHM",  "HS256")

# # ================= DATABASE =================

# engine = create_engine(URL)
# SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Base = declarative_base()


# # ================= MODEL =================

# class User(Base):
#     __tablename__ = "users"

#     id = Column(Integer, primary_key=True, index=True)
#     username = Column(String, unique=True, index=True)
#     password = Column(String)
#     created_at = Column(DateTime, default=datetime.utcnow)

# # ================= INIT =================

# def init_db():
#     Base.metadata.create_all(bind=engine)

# # ================= SECURITY =================

# def get_password_hash(password: str) -> str:
#     return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

# def verify_password(plain: str, hashed: str) -> bool:
#     return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

# def create_access_token(data: dict):
#     return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
import bcrypt
from datetime import datetime
from jose import jwt
from dotenv import load_dotenv

load_dotenv()

# ================= PRODUCTION CONFIG =================

_user     = os.getenv("POSTGRES_USER",     "your_postgres_user")
_password = os.getenv("POSTGRES_PASSWORD", "your_postgres_password")
_host     = os.getenv("POSTGRES_HOST",     "127.0.0.1")
_port     = os.getenv("POSTGRES_PORT",     "5433")
_db       = os.getenv("POSTGRES_DB",       "gm_auth")

URL        = f"postgresql+psycopg://{_user}:{_password}@{_host}:{_port}/{_db}"
SECRET_KEY = os.getenv("SECRET_KEY", "GRAPH_MIND_ULTIMATE_SECRET_KEY")
ALGORITHM  = os.getenv("ALGORITHM",  "HS256")

# ================= DATABASE =================

engine = create_engine(URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ================= MODEL =================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

# ================= INIT =================

def init_db():
    Base.metadata.create_all(bind=engine)

# ================= SECURITY =================

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(data: dict) -> str:
    token = jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)
    # python-jose returns bytes on some versions — always coerce to str
    return token.decode("utf-8") if isinstance(token, bytes) else str(token)