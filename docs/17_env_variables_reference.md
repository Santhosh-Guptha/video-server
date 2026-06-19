# Environment Variables Reference
**Project**: Enterprise Video Management System (VMS)  
**Owner**: DevOps Team  

---

| Name | Purpose | Default | Impact | Recommendations |
| :--- | :--- | :--- | :--- | :--- |
| `DATABASE_URL` | DB Connection String | `sqlite+aiosqlite:///./data/app.db` | Data persistence | Use Postgres for large scale |
| `REDIS_URL` | Redis Connection URI | `redis://127.0.0.1:6379/0` | Cache and lock storage | Run on local localhost |
| `STRICT_CAMERA_VALIDATION` | Auth Validation | `true` | Restricts un-synced push streams | Keep true for security |
| `ENABLE_H265_TRANSCODING` | Codec Transcoding | `true` | Enables HEVC viewing support | Keep true for web browsers |
| `INDEXER_INTERVAL_SECONDS` | Safety-net Indexer | `600` | Syncs DB with deleted files | Set to 600 for quick pruning |
