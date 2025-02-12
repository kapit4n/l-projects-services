# VENV
- python3 -m venv lservices
- source lservices/bin/activate


# Start projects
- cd projects/
- pip install -r requeriments.txt 
- uvicorn main:app --reload --port 8001