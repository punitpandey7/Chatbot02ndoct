# Hugging Face Spaces (Docker SDK) build for the HDFC MF FAQ assistant.
#
# Why Docker and not the Streamlit SDK: Spaces has no "build command" hook.
# With Docker we get a real RUN step, which is what lets us rebuild the
# Chroma vector DB during the image build. data/chroma/ is gitignored, so a
# fresh clone has no index and the app would show "no vector database found".

FROM python:3.11-slim

WORKDIR /app

# Build tooling. Every dependency here (torch, lxml, chromadb, onnxruntime)
# ships cp311 manylinux wheels, so this is belt-and-braces for the odd one
# that does not. Safe to drop if the image build gets slow.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so Docker caches this layer across rebuilds.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# --- Stage A: build the vector DB during the image build ---------------------
# Fetches the 7 source pages, chunks, embeds 239 chunks with MiniLM, and
# persists Chroma to data/chroma/. On total network failure it falls back to
# the committed data/raw/ cache, so this cannot silently produce an empty DB.
RUN python -m src.ingest \
    && python -m src.store

# Fail the build if the index did not actually materialise, rather than
# shipping an image whose app only shows an error page.
RUN test -f data/chroma/chroma.sqlite3 || (echo "vector DB missing after ingest" && exit 1)

# Spaces routes to this port; keep in sync with `app_port` in README.md.
EXPOSE 7860

# src/app.py sets no server address/port, so both are supplied here.
CMD ["streamlit", "run", "src/app.py", \
     "--server.port", "7860", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true", \
     "--server.enableCORS", "false", \
     "--server.enableXsrfProtection", "false"]