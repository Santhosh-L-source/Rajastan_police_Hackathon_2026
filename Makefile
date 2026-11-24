.PHONY: setup data demo run test screenshots clean

setup:
	@echo "Setting up FINTRACE..."
	pip install -r requirements.txt
	cd frontend && npm install
	@echo "Setup complete!"

data:
	@echo "Generating synthetic fraud data..."
	python scripts/generate_data.py
	@echo "Data generated in sample_data/"

demo:
	@echo "=========================================="
	@echo "Setting up FINTRACE demo case..."
	@echo "=========================================="
	@echo ""
	@echo "Step 1: Cleaning database..."
	@if exist tracefreeze.db del /q tracefreeze.db
	@if exist fintrace.db del /q fintrace.db
	@echo "OK Database reset"
	@echo ""
	@echo "Step 2: Generating demo case..."
	@python scripts/generate_demo_case.py
	@echo ""
	@echo "Step 3: Starting backend server..."
	@start /B python -m uvicorn backend.api.main:app --port 8000
	@timeout /t 5 /nobreak > nul
	@echo "OK Backend running on http://localhost:8000"
	@echo ""
	@echo "Step 4: Loading demo case into database..."
	@curl -s -X POST http://localhost:8000/cases -H "Content-Type: application/json" -d "{\"case_id\":\"case_001\",\"title\":\"Case 001 - Cyber Fraud Demo\",\"description\":\"Phishing scam with layered money laundering\",\"victim_account\":\"VICTIM_9876543210\"}" > nul
	@curl -s -X POST http://localhost:8000/cases/case_001/upload -F "files=@sample_data/case_001/DEMO_statement.csv" > nul
	@curl -s -X POST http://localhost:8000/cases/case_001/analyze -H "Content-Type: application/json" -d "{}" > nul
	@curl -s -X POST http://localhost:8000/cases/case_001/infra/upload -F "file=@sample_data/case_001/infrastructure.csv" > nul
	@echo "OK Case loaded and analyzed"
	@echo ""
	@echo "Step 5: Starting frontend..."
	@cd frontend && start /B npm run dev
	@timeout /t 5 /nobreak > nul
	@echo "OK Frontend running on http://localhost:3001"
	@echo ""
	@echo "=========================================="
	@echo "DEMO READY!"
	@echo "=========================================="
	@echo ""
	@echo "Open: http://localhost:3001"
	@echo ""

run:
	@echo "Starting FINTRACE..."
	@echo "Backend: http://localhost:8000"
	@echo "Frontend: http://localhost:3001"
	@echo ""
	start /B python -m uvicorn backend.api.main:app --reload --port 8000
	cd frontend && npm run dev

test:
	@echo "Running backend tests..."
	pytest backend/ -v

screenshots:
	@echo "=========================================="
	@echo "Capturing presentation screenshots..."
	@echo "=========================================="
	@echo ""
	@echo "Installing Playwright if needed..."
	@pip install playwright > nul 2>&1 || echo "Playwright already installed"
	@playwright install chromium > nul 2>&1 || echo "Chromium already installed"
	@echo ""
	@$(MAKE) demo
	@echo ""
	@echo "Waiting for UI to stabilize..."
	@timeout /t 10 /nobreak > nul
	@echo ""
	@echo "Capturing screenshots..."
	@python scripts/capture_screenshots.py
	@echo ""
	@echo "OK Screenshots ready in docs/screenshots/"

evaluate:
	@echo "Evaluating detection against ground truth..."
	python scripts/evaluate.py

clean:
	@echo "Cleaning up..."
	@if exist uploads rmdir /s /q uploads
	@if exist reports rmdir /s /q reports
	@if exist fintrace.db del /q fintrace.db
	@if exist docs\screenshots rmdir /s /q docs\screenshots
	@for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
	@taskkill /F /IM python.exe /FI "WINDOWTITLE eq uvicorn*" > nul 2>&1 || echo ""
	@taskkill /F /IM node.exe /FI "WINDOWTITLE eq vite*" > nul 2>&1 || echo ""
	@echo "Clean complete!"
