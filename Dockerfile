FROM python:3.11-slim

# 1. 設置環境變量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    GOLANG_VERSION=1.24.3 \
    NODE_VERSION=20 \
    NVM_DIR=/root/.nvm

WORKDIR /app

# 定義建置參數
ARG UID=0
ARG GID=0
ARG USERNAME=nate

# 2. 安裝系統依賴 (整合自 setup_environment.sh)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    sudo \
    make \
    screen \
    wget \
    tini \
    unzip \
    cmake \
    build-essential \
    g++ \
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

# 3. 安裝 Go 語言
RUN wget -q https://go.dev/dl/go${GOLANG_VERSION}.linux-amd64.tar.gz -O /tmp/go.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf /tmp/go.tar.gz \
    && rm /tmp/go.tar.gz
ENV PATH=$PATH:/usr/local/go/bin

# 4. 安裝 Node.js (使用 NodeSource 確保版本穩定)
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g pnpm typescript ts-node rimraf

# 5. 安裝 Bun Runtime
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH=$PATH:/root/.bun/bin

# 6. 安裝 Docker CLI 與 Docker Compose (二進制檔案，用於與宿主機 Docker 通訊)
RUN curl -SL https://download.docker.com/linux/static/stable/x86_64/docker-26.1.4.tgz -o /tmp/docker.tgz \
    && tar -xzvf /tmp/docker.tgz -C /tmp \
    && cp /tmp/docker/docker /usr/local/bin/ \
    && rm -rf /tmp/docker /tmp/docker.tgz \
    && curl -SL https://github.com/docker/compose/releases/download/v2.24.6/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose \
    && chmod +x /usr/local/bin/docker-compose

# 7. 安裝 Claude (假設為腳本模式)
RUN curl -fsSL https://claude.ai/install.sh | bash || true

# 8. Git 全域設定
RUN git config --global user.name 'NateYeh' \
    && git config --global user.email 'yeh.nate@gmail.com'

# 9. 處理使用者與權限邏輯 (以及 SSH 目錄準備)
RUN if [ "$UID" -ne 0 ]; then \
    groupadd -g $GID $USERNAME || true && \
    useradd -l -u $UID -g $GID -m -s /bin/bash $USERNAME || true && \
    echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME && \
    chown -R $UID:$GID /usr/local/lib/python3.11/site-packages && \
    chown -R $UID:$GID /usr/local/bin && \
    chown -R $UID:$GID /app ; \
    fi && \
    mkdir -p /home/$USERNAME/.ssh && chmod 700 /home/$USERNAME/.ssh
# 10. 搬入原始碼與設定檔
COPY --chown=$UID:$GID . .

# 11. 安裝 Python 依賴與 Playwright 瀏覽器
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e . \
    && playwright install chromium

# 12. 處理權限與啟動腳本
RUN mkdir -p logs workspace && \
    chown -R $UID:$GID logs workspace && \
    chmod +x src/mcp_server/start.sh

# 處理 Playwright 快取路徑 (針對非 root 使用者)
RUN if [ "$UID" -ne 0 ]; then \
    mkdir -p /home/$USERNAME/.cache && \
    cp -r /root/.cache/ms-playwright /home/$USERNAME/.cache/ && \
    chown -R $UID:$GID /home/$USERNAME/.cache ; \
    fi

USER $UID
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/bin/bash", "src/mcp_server/start.sh"]
