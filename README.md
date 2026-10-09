# Flask Hello World 一頁式網站

這是一個基於 Python Flask 框架建置的輕量級「Hello World」一頁式網站範例，並配置了 **GitHub Actions 與 Render 的 CI/CD 自動化部署流程**。

## 專案結構

```text
practice0929/
├── .github/
│   └── workflows/
│       └── ci-cd.yml          # GitHub Actions CI/CD 工作流程
├── templates/
│   └── index.html             # 一頁式網站前端樣板
├── app.py                     # Flask 主程式
├── test_app.py                # 單元測試 (CI 驗證)
├── render.yaml                # Render Blueprint 部署設定
├── requirements.txt           # 相依套件 (Flask, Gunicorn)
└── README.md                  # 專案說明文件
```

---

## 本地開發快速開始

1. 建立並啟用虛擬環境：
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. 安裝相依套件：
   ```bash
   pip install -r requirements.txt
   ```

3. 執行單元測試：
   ```bash
   python -m unittest test_app.py
   ```

4. 啟動伺服器：
   ```bash
   python app.py
   ```

5. 開啟瀏覽器訪問：
   [http://127.0.0.1:5000/](http://127.0.0.1:5000/)

---

## CI/CD 自動化部署設定 (GitHub Actions + Render)

本專案採用業界標準的 CI/CD 流程：
- **CI (持續整合)**：每次 Push 或 Pull Request 至 `main` 分支時，GitHub Actions 會自動執行單元測試。
- **CD (持續部署)**：測試通過後，GitHub Actions 自動呼叫 Render 的 **Deploy Hook** 觸發線上部署。

### 步驟 1：在 Render 上建立 Web Service
1. 登入 [Render](https://render.com/) 並點選 **New +** -> **Web Service**。
2. 連接您的 GitHub 倉庫 `peipeiyellow/practice0929`（或直接使用 Blueprint 匯入 `render.yaml`）。
3. 基本設定確認：
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Auto-Deploy**: 建議設為 **No / Off**（由 GitHub Actions 測試通過後才觸發部署）。

### 步驟 2：取得 Render Deploy Hook
1. 在 Render 的該服務頁面中，前往 **Settings** 分頁。
2. 往下拉找到 **Deploy Hook** 區塊。
3. 點選 **Add Deploy Hook** 或複製產生的 Hook URL（格式如：`https://api.render.com/deploy/srv-xxxx?key=yyyy`）。

### 步驟 3：在 GitHub 設定 Repository Secret
1. 開啟 GitHub 倉庫頁面：[https://github.com/peipeiyellow/practice0929](https://github.com/peipeiyellow/practice0929)
2. 點選 **Settings** -> **Secrets and variables** -> **Actions**。
3. 點選 **New repository secret**：
   - **Name**: `RENDER_DEPLOY_HOOK_URL`
   - **Secret**: 貼上剛才從 Render 複製的 Deploy Hook 網址。
4. 點選 **Add secret** 完成儲存。

完成後，每次推動程式碼到 `main` 分支，GitHub Actions 都會自動驗證測試並完成 Render 部署！
