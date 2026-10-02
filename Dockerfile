# Container image for the HDFC MF FAQ assistant.
#
# This is NOT how the app is deployed — that is Streamlit Community Cloud,
# which installs requirements.txt and needs no image. This file is here so the
# app can be run in a container locally:
#
#     docker build -t hdfc-mf-faq .
#     docker run -p 8501:8501 hdfc-mf-faq
#
# data/chroma/ is committed to the repo, so the index is already in the image
# and the build neither fetches source pages nor embeds anything.

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

# Fail loudly if the committed index did not make it into the image, rather
# than shipping a container whose app can only show an error page.
RUN test -f data/chroma/chroma.sqlite3 \
    || (echo "committed vector DB missing from image" && exit 1)

EXPOSE 8501

# Root app.py is the same entrypoint the deployment uses: it puts the repo root
# on sys.path and calls src.app.main().
CMD ["streamlit", "run", "app.py", \
     "--server.port", "8501", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true"]