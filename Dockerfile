# 7even5ive as one web service: the core, PortMax's phone API and the mock college portal
# behind one address (core/seventy5/cloud.py). Any host that runs a Dockerfile works;
# render.yaml sets it up on Render.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/core
# Dependencies first, so code changes don't reinstall them. requirements.txt installs
# PortMax from ../portmax, so PortMax's source comes in this layer too.
COPY portmax /app/portmax
COPY core/requirements.txt /app/core/requirements.txt
RUN pip install -r requirements.txt

COPY core /app/core
RUN mkdir -p data && useradd --create-home app && chown -R app /app/core/data
USER app

# Render and most hosts set PORT; 8000 otherwise.
EXPOSE 8000
CMD ["python", "-m", "seventy5.cloud"]
