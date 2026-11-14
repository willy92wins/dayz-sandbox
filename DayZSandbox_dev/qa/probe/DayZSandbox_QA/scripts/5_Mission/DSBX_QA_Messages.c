class DSBX_QA_Config
{
	string url;
	string key;
	int retry_ms;
}

class DSBX_QA_HelloResp
{
	int lease_ms;
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
