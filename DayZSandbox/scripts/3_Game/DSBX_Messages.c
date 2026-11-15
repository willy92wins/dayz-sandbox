class DSBX_PeerConfig
{
	string url;
	string key;
}

class DSBX_HelloResp
{
	bool ok;
	string session;
	int conn;
	int lease_ms;
	int hold_ms;
	int wire_cap;
}

class DSBX_Args
{
	string doc_id;
	int rev;
	string hash;
}

class DSBX_Order
{
	string op_id;
	string session;
	int conn;
	string epoch;
	string inst;
	string verb;
	ref DSBX_Args args;
	int issued_ms;
	int ttl_ms;
}

class DSBX_PollResp
{
	bool ok;
	int now_ms;
	ref array<ref DSBX_Order> ops;
}

class DSBX_AckResp
{
	bool ok;
}

class DSBX_Messages
{
	static bool IsHexChar(int c)
	{
		if (c >= 48 && c <= 57)
		{
			return true;
		}
		if (c >= 65 && c <= 70)
		{
			return true;
		}
		if (c >= 97 && c <= 102)
		{
			return true;
		}
		return false;
	}

	static bool IsHex(string s, int wantLen)
	{
		if (s.Length() != wantLen)
		{
			return false;
		}
		int i = 0;
		while (i < wantLen)
		{
			int c = s.Substring(i, 1).ToAscii();
			if (!IsHexChar(c))
			{
				return false;
			}
			i = i + 1;
		}
		return true;
	}

	static bool ValidHello(DSBX_HelloResp resp)
	{
		if (!resp)
		{
			return false;
		}
		if (!resp.ok)
		{
			return false;
		}
		if (!IsHex(resp.session, 16))
		{
			return false;
		}
		if (resp.conn < 1)
		{
			return false;
		}
		if (resp.lease_ms <= 0)
		{
			return false;
		}
		if (resp.hold_ms <= 0)
		{
			return false;
		}
		if (resp.wire_cap < 1024)
		{
			return false;
		}
		return true;
	}

	static bool ValidOrder(DSBX_Order order)
	{
		if (!order)
		{
			return false;
		}
		if (order.op_id == "")
		{
			return false;
		}
		if (!IsHex(order.session, 16))
		{
			return false;
		}
		if (order.conn < 0)
		{
			return false;
		}
		if (!IsHex(order.epoch, 32))
		{
			return false;
		}
		if (!IsHex(order.inst, 32))
		{
			return false;
		}
		if (order.verb == "")
		{
			return false;
		}
		if (!order.args)
		{
			return false;
		}
		if (order.issued_ms < 0)
		{
			return false;
		}
		if (order.ttl_ms <= 0)
		{
			return false;
		}
		return true;
	}

	static bool ValidPoll(DSBX_PollResp resp)
	{
		if (!resp)
		{
			return false;
		}
		if (!resp.ok)
		{
			return false;
		}
		if (resp.now_ms < 0)
		{
			return false;
		}
		if (!resp.ops)
		{
			return false;
		}
		if (resp.ops.Count() > 1)
		{
			return false;
		}
		if (resp.ops.Count() == 1 && !ValidOrder(resp.ops.Get(0)))
		{
			return false;
		}
		return true;
	}

	static bool ValidAck(DSBX_AckResp resp)
	{
		if (!resp)
		{
			return false;
		}
		if (!resp.ok)
		{
			return false;
		}
		return true;
	}
}
