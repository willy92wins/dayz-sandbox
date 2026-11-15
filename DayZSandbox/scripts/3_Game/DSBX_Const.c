const int DSBX_WIRE_CAP = 3500;
const int DSBX_RPC_EPOCH = 26111501;
const int DSBX_RPC_EPOCH_REQ = 26111502;

class DSBX_Const
{
	const int ST_SIN_CONFIG = 0;
	const int ST_HELLO = 1;
	const int ST_LISTO = 2;

	const int CH_P = 1;
	const int CH_R = 2;

	const int KIND_HELLO = 1;
	const int KIND_POLL = 2;
	const int KIND_KEEPALIVE = 3;
	const int KIND_RESULT = 4;
	const int KIND_CATALOG = 5;

	const int CACHE_EN_CURSO = 1;
	const int CACHE_TERMINADA = 2;

	const int DEFAULT_LEASE_MS = 3000;
	const int DEFAULT_HOLD_MS = 2000;
	const int DEFAULT_RETRY_MS = 2000;
	const int KEEPALIVE_MS = 500;
	const int DEADLINE_MARGIN_MS = 100;
	const int RETENTION_EXTRA_MS = 1000;
	const int CACHE_CAP = 1024;
	const int BASE_BACKOFF_MS = 250;
	const int WATCHDOG_MS = 6000;
	const int EPOCH_REQ_MS = 2000;
	const int CALLBACK_POOL_MAX = 4;
	const int CALLBACK_BUDGET = 2000;
	const int CATALOG_SCAN_BATCH = 200;
	const int R_MAX_FAILURES = 4;

	const string MOD_VER = "0.1.0";
	const string EMPTY_REG_SHA256 = "0000000000000000000000000000000000000000000000000000000000000000";
}
