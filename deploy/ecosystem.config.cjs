// pm2 process for taxqa.soniksarungale.com.
// Start: pm2 start deploy/ecosystem.config.cjs && pm2 save
// One worker: the embedding model is loaded once per process, and the server has 2 GB of RAM.
// --proxy-headers takes the client address from nginx, so the per-address rate limit works.
module.exports = {
  apps: [{
    name: 'taxqa',
    cwd: `${__dirname}/..`,
    script: '.venv/bin/uvicorn',
    args: 'taxqa.app:app --host 127.0.0.1 --port 4700 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1',
    interpreter: 'none',
    exec_mode: 'fork',
    instances: 1,
    autorestart: true,
    max_memory_restart: '450M',
    restart_delay: 3000,
    out_file: 'logs/out.log',
    error_file: 'logs/error.log',
    merge_logs: true,
    time: true,
  }],
};
