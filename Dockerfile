FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

# Create default state directories
RUN mkdir -p /app/.state /app/.cache

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["hermes"]
CMD ["workbench", "serve", "--host", "0.0.0.0", "--port", "8000"]
