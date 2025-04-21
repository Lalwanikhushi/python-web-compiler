from datetime import datetime
from main import db

class CodeSnippet(db.Model):
    __tablename__ = 'code_snippets'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    code = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(200))
    language = db.Column(db.String(50), default='python')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<CodeSnippet {self.title}>"
    
    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'code': self.code,
            'description': self.description,
            'language': self.language,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }