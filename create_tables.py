
from database import Base, engine
from db_models import IncidentRecord


Base.metadata.create_all(bind=engine)

print("Database tables created successfully!")

