from sqlalchemy import text 
from sqlalchemy.exc import SQLAlchemyError


from database import SessionLocal

db = SessionLocal()

try:
    db.execute(
        text("SELECT * FROM table_that_does_not_exist")
    )
    db.commit()

except SQLAlchemyError as error:
    print("Database operation failed")
    print(type(error).__name__)
    
    
    db.rollback()
    print("Transaction rolled back succesfully.")
    
finally:
    db.close()