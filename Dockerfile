FROM python:3.8-slim

RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list

RUN apt-get update && \
    apt-get install -y --no-install-recommends make ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-server.txt .

RUN pip install --no-cache-dir -r requirements-server.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

EXPOSE 6016

CMD ["python3", "./start_server.py"]