from typing import Annotated

from fastapi import Depends, Query
from sqlmodel import Field, Session, SQLModel, create_engine

sqlite_file_name = 'database.db'
sqlite_url = f'sqlite:///{sqlite_file_name}'

connect_args = {'check_same_thread': False}
engine = create_engine(sqlite_url, connect_args=connect_args)

class NetBoxEndpoint(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    ip_address: str = Field(index=True)
    port: int = Field(default=443)
    token: str = Field()
    verify_ssl: bool = Field(default=True)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]