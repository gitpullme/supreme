# SAT-SA — air-gap deploy image (CPU-only, no GPU, no network at runtime).
# Build ONCE on an internet-connected build host, export, move via approved
# offline media, import on the NCIIPC host. Runtime needs zero connectivity.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /satsa
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY satsa/ ./satsa/
COPY rules/ ./rules/
COPY attck/ ./attck/
COPY api.py dashboard.py run.py ./
COPY frontend/dist/ ./frontend/dist/

# Pre-bake the demo dataset at build time so first boot is instant.
RUN python run.py

EXPOSE 8000
CMD ["python", "run.py", "--serve"]
