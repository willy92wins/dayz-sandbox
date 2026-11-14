class DSBX_QA_Config
{
	string url;
	string key;
	int retry_ms;
	int callback_budget;
}

class DSBX_QA_HelloResp
{
	int lease_ms;
	bool ok;
}

class DSBX_QA_AckResp
{
	bool ok;
}

class DSBX_QA_PollResp
{
	float now_ms;
	ref array<ref DSBX_QA_Op> ops;
}

class DSBX_QA_Op
{
	string op_id;
	string verb;
	string inst;
	float issued_ms;
	int ttl_ms;
	ref DSBX_QA_Args args;
}

class DSBX_QA_Args
{
	float x;
	float z;
	float fog;
	ref array<float> pos;
	ref array<float> ypr;
	int count;
	int interval_ms;
	int seq0;
	string client_inst;
	ref array<string> sk;
	ref array<string> sv;
	ref array<string> nk;
	ref array<float> nv;
	ref array<string> ncol;
	ref array<float> ncell;
	ref array<string> scol;
	ref array<string> scell;
	int rows;
}

class DSBX_QA_Result
{
	string op_id;
	string status;
	string reason;
	int dup;
	float recv_ms;
	float done_ms;
	int frame_recv;
	int frame_done;
	ref DSBX_QA_Read read;

	void DSBX_QA_Result()
	{
		read = new DSBX_QA_Read();
	}
}

class DSBX_QA_Read
{
	ref array<string> has;
	int frame;
	float tick_s;
	float y;
	float fog;
	ref array<float> pos;
	ref array<float> ypr;
	ref array<ref DSBX_QA_RpcEntry> rpc_log;
	ref array<string> sk;
	ref array<string> sv;
	ref array<string> nk;
	ref array<float> nv;
	ref array<string> ncol;
	ref array<float> ncell;
	ref array<string> scol;
	ref array<string> scell;
	int rows;

	void DSBX_QA_Read()
	{
		has = new array<string>();
		pos = new array<float>();
		pos.Insert(0.0);
		pos.Insert(0.0);
		pos.Insert(0.0);
		ypr = new array<float>();
		ypr.Insert(0.0);
		ypr.Insert(0.0);
		ypr.Insert(0.0);
		rpc_log = new array<ref DSBX_QA_RpcEntry>();
		sk = new array<string>();
		sv = new array<string>();
		nk = new array<string>();
		nv = new array<float>();
		ncol = new array<string>();
		ncell = new array<float>();
		scol = new array<string>();
		scell = new array<string>();
		rows = 0;
	}
}

class DSBX_QA_RpcEntry
{
	int seq;
	float recv_ms;
	float lease_age_ms;
	string decision;

	void DSBX_QA_RpcEntry()
	{
		seq = 0;
		recv_ms = 0.0;
		lease_age_ms = 0.0;
		decision = "";
	}
}
