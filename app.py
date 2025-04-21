import os
import logging
import tempfile
import shutil
import traceback
import py_compile
import sys
import io
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, flash, jsonify, session
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "dev_secret_key")

# Configure SQLAlchemy
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
db.init_app(app)

# Configuration
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'python_compiler')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {'py'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1MB max file size

# Define database models
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


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def cleanup_temp_files():
    """Clean up temporary files and directories."""
    if os.path.exists(UPLOAD_FOLDER):
        try:
            # Don't remove the directory, just clean out files older than 30 minutes
            current_time = time.time()
            for file_name in os.listdir(UPLOAD_FOLDER):
                file_path = os.path.join(UPLOAD_FOLDER, file_name)
                # Check if it's a file and older than 30 minutes
                if os.path.isfile(file_path) and (current_time - os.path.getmtime(file_path)) > (30 * 60):
                    os.remove(file_path)
        except Exception as e:
            logger.error(f"Error cleaning up temp files: {e}")


def compile_python_file(filepath):
    """Compile a Python file and return any errors."""
    try:
        py_compile.compile(filepath, doraise=True)
        return None, True
    except py_compile.PyCompileError as e:
        return str(e), False
    except Exception as e:
        return traceback.format_exc(), False


def execute_python_code(filepath):
    """Execute a Python file and capture its output."""
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    # Create a new environment for execution
    original_sys_path = sys.path.copy()
    sys.path.insert(0, os.path.dirname(filepath))
    
    result = {
        'stdout': '',
        'stderr': '',
        'exception': '',
        'success': False
    }
    
    try:
        # Capture stdout and stderr
        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
            # Execute the Python file
            with open(filepath, 'r') as f:
                code = f.read()
                compiled_code = compile(code, filepath, 'exec')
                exec(compiled_code, {})
        
        result['stdout'] = stdout_capture.getvalue()
        result['stderr'] = stderr_capture.getvalue()
        result['success'] = True
    except Exception as e:
        result['exception'] = traceback.format_exc()
    finally:
        # Restore sys.path
        sys.path = original_sys_path
    
    return result


@app.route('/')
def index():
    """Render the main page."""
    # Clean up any temporary files
    cleanup_temp_files()
    # Get saved code snippets for display
    snippets = CodeSnippet.query.order_by(CodeSnippet.updated_at.desc()).all()
    return render_template('index.html', snippets=snippets)


@app.route('/save-snippet', methods=['POST'])
def save_snippet():
    """Save a code snippet to the database."""
    data = request.get_json()
    if not data or 'code' not in data or not data['code'].strip():
        return jsonify({'error': 'No code provided'}), 400
    
    if 'title' not in data or not data['title'].strip():
        return jsonify({'error': 'No title provided'}), 400
    
    # Check if we're updating an existing snippet
    snippet_id = data.get('id')
    if snippet_id:
        snippet = CodeSnippet.query.get(snippet_id)
        if not snippet:
            return jsonify({'error': 'Snippet not found'}), 404
        snippet.title = data['title']
        snippet.code = data['code']
        snippet.description = data.get('description', '')
        message = 'Code snippet updated successfully'
    else:
        # Create a new snippet
        snippet = CodeSnippet(
            title=data['title'],
            code=data['code'],
            description=data.get('description', ''),
            language='python'
        )
        db.session.add(snippet)
        message = 'Code snippet saved successfully'
    
    db.session.commit()
    
    return jsonify({
        'message': message,
        'snippet': snippet.to_dict()
    })


@app.route('/load-snippet/<int:snippet_id>', methods=['GET'])
def load_snippet(snippet_id):
    """Load a code snippet from the database."""
    snippet = CodeSnippet.query.get(snippet_id)
    if not snippet:
        return jsonify({'error': 'Snippet not found'}), 404
    
    return jsonify(snippet.to_dict())


@app.route('/delete-snippet/<int:snippet_id>', methods=['DELETE'])
def delete_snippet(snippet_id):
    """Delete a code snippet from the database."""
    snippet = CodeSnippet.query.get(snippet_id)
    if not snippet:
        return jsonify({'error': 'Snippet not found'}), 404
    
    db.session.delete(snippet)
    db.session.commit()
    
    return jsonify({'message': 'Code snippet deleted successfully'})


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and compilation."""
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return jsonify({'error': 'No file part'}), 400
    
    files = request.files.getlist('file')
    
    if not files or all(file.filename == '' for file in files):
        flash('No selected file', 'danger')
        return jsonify({'error': 'No selected file'}), 400
    
    uploaded_files = []
    compile_results = []
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            uploaded_files.append(filepath)
            
            # Compile the file
            error, success = compile_python_file(filepath)
            compile_results.append({
                'filename': filename,
                'success': success,
                'error': error,
                'filepath': filepath
            })
        else:
            flash(f'Invalid file: {file.filename}. Only Python files (.py) are allowed.', 'danger')
    
    session['uploaded_files'] = uploaded_files
    
    return jsonify({
        'message': 'Files uploaded successfully' if uploaded_files else 'No valid files uploaded',
        'compile_results': compile_results
    })


@app.route('/compile-code', methods=['POST'])
def compile_code():
    """Handle direct code input and compilation."""
    data = request.get_json()
    if not data or 'code' not in data or not data['code'].strip():
        return jsonify({'error': 'No code provided'}), 400
    
    # Generate a random filename for the code
    import uuid
    filename = f"code_{uuid.uuid4().hex[:8]}.py"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # Write the code to a temporary file
    try:
        with open(filepath, 'w') as f:
            f.write(data['code'])
        
        # Compile the file
        error, success = compile_python_file(filepath)
        compile_result = {
            'filename': filename,
            'success': success,
            'error': error,
            'filepath': filepath
        }
        
        # Add to session for cleanup later
        if 'uploaded_files' not in session:
            session['uploaded_files'] = []
        session['uploaded_files'].append(filepath)
        
        return jsonify({
            'message': 'Code compiled successfully' if success else 'Compilation failed',
            'compile_results': [compile_result]
        })
    except Exception as e:
        logger.error(f"Error handling code input: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/execute', methods=['POST'])
def execute_code():
    """Execute uploaded Python code."""
    data = request.get_json()
    if not data or 'filepath' not in data:
        return jsonify({'error': 'No filepath provided'}), 400
    
    filepath = data['filepath']
    
    # Verify the file is in the upload directory for security
    if not os.path.normpath(filepath).startswith(os.path.normpath(app.config['UPLOAD_FOLDER'])):
        return jsonify({'error': 'Invalid filepath'}), 400
    
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    # Execute the Python code
    result = execute_python_code(filepath)
    return jsonify(result)


@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error."""
    flash('File too large. Maximum size is 1MB.', 'danger')
    return render_template('index.html'), 413


@app.teardown_appcontext
def teardown_db(exception=None):
    """Clean up resources when the application context ends."""
    cleanup_temp_files()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
