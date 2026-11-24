.PHONY: setup data run test clean

setup:
	@echo "Setting up TraceFreeze..."
	pip install -r requirements.txt
	cd frontend && npm install
	@echo "Setup complete!"

data:
	@echo "Generating synthetic fraud data..."
	python scripts/generate_data.py
	@echo "Data generated in sample_data/"

run:
	@echo "Starting TraceFreeze..."
	@echo "Backend: http://localhost:8000"
	@echo "Frontend: http://localhost:3000"
	@echo ""
	@echo "Starting servers (Ctrl+C to stop)..."
	python -m uvicorn backend.api.main:app --reload --port 8000 &
	cd frontend && npm run dev

test:
	@echo "Running backend tests..."
	pytest backend/ -v

evaluate:
	@echo "Evaluating detection against ground truth..."
	python scripts/evaluate.py

clean:
	@echo "Cleaning up..."
	rm -rf uploads/ reports/ *.db frontend/node_modules/ frontend/dist/
	find . -type d -name __pycache__ -exec rm -rf {} +
	@echo "Clean complete!"
