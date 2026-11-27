// S-track·2 server side: dresses ropa and moves the suave Pot.
// The case arrives from the client via STRACK_UDT_CASE (STRACK_Move.c);
// the server never sees the client's -strack* arguments.

class STRACK_Server
{
	static bool s_RopaDone;
	static EntityAI s_Pot;
	static vector s_PotBase;
	static int s_PotI;
	static int s_SrvFrame;
	static float s_PotAcc;

	static void TickSrv(float dt)
	{
		array<Man> players;
		PlayerBase player;
		int caso;
		if (!GetGame() || !GetGame().IsServer())
		{
			return;
		}
		s_SrvFrame = s_SrvFrame + 1;
		players = new array<Man>();
		GetGame().GetPlayers(players);
		if (players.Count() == 0)
		{
			return;
		}
		player = PlayerBase.Cast(players.Get(0));
		if (!player)
		{
			return;
		}
		caso = STRACK_Move.ServerCase();
		if (caso == 1)
		{
			DressRopa(player);
		}
		if (caso == 2)
		{
			TickPot(player, dt);
		}
	}

	static void ResendPotId(PlayerBase player)
	{
		int netLow;
		int netHigh;
		ScriptRPC rpc;
		if (!s_Pot)
		{
			return;
		}
		if (!player)
		{
			return;
		}
		if (!GetGame() || !GetGame().IsServer())
		{
			return;
		}
		netLow = 0;
		netHigh = 0;
		s_Pot.GetNetworkID(netLow, netHigh);
		STRACK_Session.SetPotId(netLow, netHigh);
		if (GetGame().IsMultiplayer() && player.GetIdentity())
		{
			rpc = new ScriptRPC();
			rpc.Write(netLow);
			rpc.Write(netHigh);
			rpc.Send(player, STRACK_RPC_POT, true, player.GetIdentity());
			Print("[STRACK] suave lata netid reenviado nueva corrida");
		}
	}

	protected static void DressRopa(PlayerBase player)
	{
		HumanInventory inv;
		EntityAI weapon;
		EntityAI made;
		if (s_RopaDone)
		{
			return;
		}
		inv = player.GetHumanInventory();
		if (!inv)
		{
			return;
		}
		weapon = inv.GetEntityInHands();
		if (!weapon)
		{
			return;
		}
		made = player.GetInventory().CreateAttachment("AliceBag_Green");
		if (!made)
		{
			Print("[STRACK] ropa AliceBag_Green fallo");
		}
		made = weapon.GetInventory().CreateAttachment("ACOGOptic");
		if (!made)
		{
			Print("[STRACK] ropa ACOGOptic fallo");
		}
		made = weapon.GetInventory().CreateAttachment("M4_Suppressor");
		if (!made)
		{
			Print("[STRACK] ropa M4_Suppressor fallo");
		}
		s_RopaDone = true;
		Print("[STRACK] ropa vestido");
	}

	protected static void TickPot(PlayerBase player, float dt)
	{
		vector pos;
		vector fwd;
		Object created;
		int netLow;
		int netHigh;
		ScriptRPC rpc;
		if (STRACK_Move.ServerPotFrozen())
		{
			return;
		}
		if (!s_Pot)
		{
			pos = player.GetPosition();
			fwd = player.GetDirection();
			fwd[1] = 0;
			if (fwd.Length() < 0.001)
			{
				fwd = Vector(0, 0, 1);
			}
			fwd.Normalize();
			s_PotBase = pos + fwd * 3.0;
			s_PotBase[1] = GetGame().SurfaceY(s_PotBase[0], s_PotBase[2]);
			created = GetGame().CreateObject("Pot", s_PotBase, false);
			s_Pot = EntityAI.Cast(created);
			if (!s_Pot)
			{
				Print("[STRACK] suave Pot fallo");
				return;
			}
			s_Pot.DisableSimulation(true);
			s_Pot.SetPosition(s_PotBase);
			s_PotI = 0;
			s_PotAcc = 0.0;
			Print("[STRACK] suave lata creada pos=" + STRACK_Math.V(s_PotBase));
			netLow = 0;
			netHigh = 0;
			s_Pot.GetNetworkID(netLow, netHigh);
			STRACK_Session.SetPotId(netLow, netHigh);
			if (GetGame().IsMultiplayer() && player.GetIdentity())
			{
				rpc = new ScriptRPC();
				rpc.Write(netLow);
				rpc.Write(netHigh);
				rpc.Send(player, STRACK_RPC_POT, true, player.GetIdentity());
				Print("[STRACK] suave lata netid enviado");
			}
			return;
		}
		s_PotAcc = s_PotAcc + dt;
		if (s_PotAcc < 2.0)
		{
			return;
		}
		s_PotAcc = 0.0;
		s_PotI = s_PotI + 1;
		pos = s_PotBase;
		if ((s_PotI % 2) == 1)
		{
			pos[0] = pos[0] + 1.0;
		}
		s_Pot.SetPosition(pos);
		Print("[STRACK] suave salto i=" + s_PotI.ToString() + " frame_srv=" + s_SrvFrame.ToString() + " t_srv_ms=" + GetGame().GetTime().ToString() + " pos=" + STRACK_Math.V(pos));
	}
};
