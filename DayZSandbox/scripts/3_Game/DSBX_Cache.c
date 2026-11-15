class DSBX_CacheEntry
{
	string m_CacheKey;
	ref DSBX_Order m_Order;
	int m_State;
	string m_Status;
	string m_Reason;
	string m_ReadJson;
	int m_StepsDone;
	float m_PlazoLocal;
	float m_RetencionHasta;
	int m_Attempts;
	float m_NextAttemptMs;
	bool m_Pending;
	bool m_SendDup;

	void DSBX_CacheEntry(string cacheKey, DSBX_Order order, float plazoLocal, float retencionHasta)
	{
		m_CacheKey = cacheKey;
		m_Order = order;
		m_State = DSBX_Const.CACHE_EN_CURSO;
		m_Status = "";
		m_Reason = "";
		m_ReadJson = "{}";
		m_StepsDone = 0;
		m_PlazoLocal = plazoLocal;
		m_RetencionHasta = retencionHasta;
		m_Attempts = 0;
		m_NextAttemptMs = 0.0;
		m_Pending = false;
		m_SendDup = false;
	}
}

class DSBX_Cache
{
	int m_Cap;
	ref map<string, ref DSBX_CacheEntry> m_Entries;
	ref array<string> m_Order;

	void DSBX_Cache(int cap)
	{
		m_Cap = cap;
		m_Entries = new map<string, ref DSBX_CacheEntry>();
		m_Order = new array<string>();
	}

	int Size()
	{
		return m_Order.Count();
	}

	DSBX_CacheEntry GetLive(string cacheKey, float now)
	{
		if (!m_Entries.Contains(cacheKey))
		{
			return null;
		}
		DSBX_CacheEntry entry = m_Entries.Get(cacheKey);
		if (entry && entry.m_RetencionHasta > now)
		{
			return entry;
		}
		m_Entries.Remove(cacheKey);
		int i = 0;
		while (i < m_Order.Count())
		{
			if (m_Order.Get(i) == cacheKey)
			{
				m_Order.RemoveOrdered(i);
				return null;
			}
			i = i + 1;
		}
		return null;
	}

	bool EvictOneExpired(float now)
	{
		int i = 0;
		while (i < m_Order.Count())
		{
			string k = m_Order.Get(i);
			DSBX_CacheEntry entry = m_Entries.Get(k);
			if (!entry || entry.m_RetencionHasta <= now)
			{
				m_Order.RemoveOrdered(i);
				m_Entries.Remove(k);
				return true;
			}
			i = i + 1;
		}
		return false;
	}

	bool MakeRoom(float now)
	{
		while (m_Order.Count() >= m_Cap)
		{
			if (!EvictOneExpired(now))
			{
				return false;
			}
		}
		return true;
	}

	bool HasFullLive(float now)
	{
		if (m_Order.Count() < m_Cap)
		{
			return false;
		}
		int i = 0;
		while (i < m_Order.Count())
		{
			string k = m_Order.Get(i);
			DSBX_CacheEntry entry = m_Entries.Get(k);
			if (!entry || entry.m_RetencionHasta <= now)
			{
				return false;
			}
			i = i + 1;
		}
		return true;
	}

	void Put(DSBX_CacheEntry entry)
	{
		if (!entry)
		{
			return;
		}
		if (!m_Entries.Contains(entry.m_CacheKey))
		{
			m_Order.Insert(entry.m_CacheKey);
		}
		m_Entries.Set(entry.m_CacheKey, entry);
	}
}
