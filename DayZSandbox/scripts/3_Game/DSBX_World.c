class DSBX_Generation
{
	string session;
	string op_id;
	int rev;
	string hash;

	void DSBX_Generation(string s, string opId, int r, string h)
	{
		session = s;
		op_id = opId;
		rev = r;
		hash = h;
	}
}

class DSBX_World
{
	string m_Epoch;
	ref DSBX_Generation m_Generation;
	int m_RegistryN;
	string m_RegistrySha256;

	void DSBX_World()
	{
		m_Epoch = "";
		m_Generation = null;
		m_RegistryN = 0;
		m_RegistrySha256 = DSBX_Const.EMPTY_REG_SHA256;
	}

	void InitServer()
	{
		m_Epoch = DSBX_Wire.MakeUuid32();
		m_Generation = null;
		m_RegistryN = 0;
		m_RegistrySha256 = DSBX_Const.EMPTY_REG_SHA256;
	}

	string GetEpoch()
	{
		return m_Epoch;
	}

	DSBX_Generation GetGeneration()
	{
		return m_Generation;
	}

	void SetGeneration(DSBX_Generation gen)
	{
		m_Generation = gen;
	}

	int GetRegistryN()
	{
		return m_RegistryN;
	}

	string GetRegistrySha256()
	{
		return m_RegistrySha256;
	}
}
