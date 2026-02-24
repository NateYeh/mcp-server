FROM python:3.11-slim

# 設置環境變量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# 定義建置參數 (預設為 root 0:0)
ARG UID=0
ARG GID=0
ARG USERNAME=nate

# 安裝系統依賴 (含 sudo)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    sudo \
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

# 處理使用者與權限邏輯
RUN if [ "$UID" -ne 0 ]; then \
    groupadd -g $GID $USERNAME || true && \
    useradd -l -u $UID -g $GID -m -s /bin/bash $USERNAME || true && \
    echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME && \
    chmod 0440 /etc/sudoers.d/$USERNAME && \
    # 授權使用者安裝 Python 套件工具
    chown -R $UID:$GID /usr/local/lib/python3.11/site-packages && \
    chown -R $UID:$GID /usr/local/bin && \
    chown -R $UID:$GID /app ; \
    fi

# 1. 搬入 pyproject.toml 與 README.md
COPY --chown=$UID:$GID pyproject.toml README.md ./

# 2. 搬入原始碼 (切換身分前先確保 root 權限安裝)
COPY --chown=$UID:$GID src ./src

# 3. 安裝 Python 套件 (此時仍以 root 操作或由 chown 後的使用者操作)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# 4. 安裝 Playwright 瀏覽器 (放在 root 下，之後會處理權限)
RUN playwright install chromium

# 處理 Playwright 快取路徑 (如果是非 root 使用者，需要移動或授權快取目錄)
RUN if [ "$UID" -ne 0 ]; then \
    mkdir -p /home/$USERNAME/.cache && \
    cp -r /root/.cache/ms-playwright /home/$USERNAME/.cache/ && \
    chown -R $UID:$GID /home/$USERNAME/.cache ; \
    fi

# 5. 搬入剩下所有內容
COPY --chown=$UID:$GID . .

# 建立預設目錄並確保權限
RUN mkdir -p logs workspace && chown -R $UID:$GID logs workspace

# 切換到指定身分 (若 UID=0 則切換回 root)
USER $UID

EXPOSE 8000

# 安裝 tini 以正確處理健康檢查與殭屍進程
RUN apt-get update && apt-get install -y tini && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["/usr/bin/tini", "--"]

# 啟動命令
CMD ["python", "-m", "mcp_server"]
