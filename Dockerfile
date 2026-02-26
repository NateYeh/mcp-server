FROM python:3.11-slim

# 設置環境變量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    GOLANG_VERSION=1.24.3

WORKDIR /app

# 定義建置參數 (預設為 root 0:0)
ARG UID=0
ARG GID=0
ARG USERNAME=nate

# 1. 安裝系統依賴 (整合 setup_environment.sh 中的 make, screen, wget)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    sudo \
    make \
    screen \
    wget \
    tini \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 2. 安裝 Go 語言 (來自 setup_environment.sh)
RUN wget -q https://go.dev/dl/go${GOLANG_VERSION}.linux-amd64.tar.gz -O /tmp/go.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz
ENV PATH=$PATH:/usr/local/go/bin

# 處理使用者與權限邏輯
RUN if [ "$UID" -ne 0 ]; then \
    groupadd -g $GID $USERNAME || true && \
    useradd -l -u $UID -g $GID -m -s /bin/bash $USERNAME || true && \
    echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME && \
    chown -R $UID:$GID /usr/local/lib/python3.11/site-packages && \
    chown -R $UID:$GID /usr/local/bin && \
    chown -R $UID:$GID /app ; \
    fi

# 3. 搬入 pyproject.toml 與 README.md
COPY --chown=$UID:$GID pyproject.toml README.md ./

# 4. 之前提到的專案開發安裝 (由於在 Docker 內部路徑不同，我們優先安裝 mcp-server 自身)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# 5. 安裝 Playwright 瀏覽器
RUN playwright install chromium

# 處理 Playwright 快取路徑
RUN if [ "$UID" -ne 0 ]; then \
    mkdir -p /home/$USERNAME/.cache && \
    cp -r /root/.cache/ms-playwright /home/$USERNAME/.cache/ && \
    chown -R $UID:$GID /home/$USERNAME/.cache ; \
    fi

# 6. 搬入原始碼與剩下所有內容
COPY --chown=$UID:$GID . .

# 建立預設目錄並確保權限
RUN mkdir -p logs workspace && chown -R $UID:$GID logs workspace

# 切換到指定身分
USER $UID

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]

# 啟動命令
CMD ["python", "-m", "mcp_server"]
