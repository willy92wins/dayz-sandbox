// Optional -strack_move=self. Owner and server both apply
// OverrideMovementSpeed / OverrideMovementAngle (human.c:253-256), same split
// as MCP_PlayerMove: the owner's overrides alone do not walk a multiplayer pawn.
// Turn is a steered walk (speed 1, angle toward +180 compass), not a pure
// in-place animation: the override has no separate turn-in-place value.

const int STRACK_UDT_MOVE = 78541091;
const int STRACK_UDT_CASE = 78541092;
const int STRACK_RPC_POT = 78541093;
const int STRACK_RPC_POT_ACK = 78541094;

class STRACK_Move
{
	static bool s_Want;
	static bool s_ServerOn;
	static bool s_RaiseOwner;
	static bool s_RaiseServer;
	static int s_Seg;
	static float s_SegT0;
	static float s_Target;
	static bool s_TurnInited;
	static float s_ServerSpeed;
	static float s_ServerAngle;
	static float s_ServerAim;
	// S-track·2: 180 deg in ~4.0 s at 60 fps (was ~1.75 s with 0.002/0.08).
	// OwnerTick scales the aim step by dt so the duration is FPS-independent.
	static float s_AimGain = 0.000875;
	static float s_AimMax = 0.035;
	static float s_ServerUntil;
	static float s_Dt = 0.0167;
	static int s_LocalCase;
	static int s_ServerCase;
	static int s_ServerTramo;
	static bool s_ServerFin;
	static int s_LocalTramo;
	static bool s_LocalFin;
	static string s_PendCaso;
	static int s_PendTramo;
	static bool s_PendFin;
	static bool s_PendActive;
	static bool s_FrozenAck;
	static int s_FrozenAckTramo;
	static bool s_Tramo4Sent;
	static bool s_ServerRunEnded;

	// Brief v1.1 (hilo, 2026-11-11): en lookat el jugador no anda; solo gira tres veces en el sitio,
	// con 1 s quieto entre giros (los tramos de andar se sustituyen por esperas).
	static bool s_NoWalk;

	static void Begin(bool noWalk)
	{
		s_NoWalk = noWalk;
		s_Want = true;
		s_Seg = 0;
		s_TurnInited = false;
		s_SegT0 = 0.0;
		if (GetGame())
		{
			s_SegT0 = GetGame().GetTickTime();
		}
		if (s_NoWalk)
		{
			Print("[STRACK] move self: 3 giros en el sitio (lookat, sin andar)");
		}
		else
		{
			Print("[STRACK] move self: 3 tandas andar/girar/andar");
		}
	}

	static void Stop()
	{
		PlayerBase player;
		if (!s_Want && !s_ServerOn)
		{
			return;
		}
		s_Want = false;
		s_ServerOn = false;
		player = null;
		if (GetGame())
		{
			player = PlayerBase.Cast(GetGame().GetPlayer());
		}
		if (player)
		{
			Release(player, s_RaiseOwner);
			s_RaiseOwner = false;
		}
		Send(-1.0, 0.0, 0.0);
		Print("[STRACK] move self parado");
	}

	static int Seg()
	{
		return s_Seg;
	}

	static int Giro()
	{
		if ((s_Seg % 3) == 1)
		{
			return (s_Seg / 3) + 1;
		}
		return 0;
	}

	static int CaseCode(string caso)
	{
		if (caso == "ropa")
		{
			return 1;
		}
		if (caso == "suave30" || caso == "suave60" || caso == "suave144")
		{
			return 2;
		}
		return 0;
	}

	static void SendCase(string caso)
	{
		SendCaseState(caso, 0, false);
	}

	// Wire: STRACK_UDT_CASE + code + tramo (0 fuera de suave) + fin (0/1).
	// If CanStoreInputUserData() is false the state stays pending and
	// FlushPending() retries it every frame; a periodic tramo resend never
	// overwrites a pending tramo==4/fin (that was the lost pot stop).
	static void SendCaseState(string caso, int tramo, bool fin)
	{
		int code;
		int effTramo;
		code = CaseCode(caso);
		s_LocalCase = code;
		if (code == 0)
		{
			return;
		}
		effTramo = tramo;
		if (fin)
		{
			s_Tramo4Sent = false;
		}
		else if (effTramo == 4)
		{
			s_Tramo4Sent = true;
		}
		else if (s_Tramo4Sent)
		{
			effTramo = 4;
		}
		s_LocalTramo = effTramo;
		s_LocalFin = fin;
		if (s_PendActive && !fin && effTramo != 4 && effTramo != s_PendTramo)
		{
			return;
		}
		s_PendCaso = caso;
		s_PendTramo = effTramo;
		s_PendFin = fin;
		s_PendActive = true;
		FlushPending();
	}

	static void ServerMarkNewRun()
	{
		s_ServerRunEnded = true;
	}

	static bool HasPending()
	{
		return s_PendActive;
	}

	static void FlushPending()
	{
		ScriptInputUserData message;
		int code;
		int finInt;
		if (!s_PendActive)
		{
			return;
		}
		if (!GetGame() || !GetGame().IsMultiplayer() || !GetGame().IsClient())
		{
			// Single-player / same process: s_Local* already is the server state.
			s_PendActive = false;
			return;
		}
		if (!ScriptInputUserData.CanStoreInputUserData())
		{
			return;
		}
		code = CaseCode(s_PendCaso);
		if (code == 0)
		{
			s_PendActive = false;
			return;
		}
		finInt = 0;
		if (s_PendFin)
		{
			finInt = 1;
		}
		message = new ScriptInputUserData();
		message.Write(STRACK_UDT_CASE);
		message.Write(code);
		message.Write(s_PendTramo);
		message.Write(finInt);
		message.Send();
		s_PendActive = false;
		Print("[STRACK] case enviado tramo=" + s_PendTramo.ToString() + " fin=" + finInt.ToString());
	}

	static void ClearFrozenAck()
	{
		s_FrozenAck = false;
		s_FrozenAckTramo = 0;
	}

	static void NoteFrozenAck(int tramo, int finInt)
	{
		s_FrozenAck = true;
		s_FrozenAckTramo = tramo;
		Print("[STRACK] suave parada confirmada por servidor tramo=" + tramo.ToString() + " fin=" + finInt.ToString());
	}

	static bool FrozenAckReceived()
	{
		return s_FrozenAck;
	}

	static void ReadCase(PlayerBase player, ParamsReadContext ctx)
	{
		int code;
		int tramo;
		int finInt;
		bool isNewRun;
		ScriptRPC ack;
		code = 0;
		tramo = 0;
		finInt = 0;
		isNewRun = false;
		if (!ctx.Read(code))
		{
			Print("[STRACK] case RPC lectura incompleta");
			return;
		}
		if (!ctx.Read(tramo))
		{
			Print("[STRACK] case RPC lectura incompleta");
			return;
		}
		if (!ctx.Read(finInt))
		{
			Print("[STRACK] case RPC lectura incompleta");
			return;
		}
		if (finInt != 0)
		{
			s_ServerCase = code;
			s_ServerTramo = tramo;
			s_ServerFin = true;
			s_ServerRunEnded = true;
		}
		else if (s_ServerRunEnded)
		{
			isNewRun = true;
			s_ServerRunEnded = false;
			s_ServerCase = code;
			s_ServerTramo = tramo;
			s_ServerFin = false;
		}
		else if (code == 2 && s_ServerCase == 2 && tramo < s_ServerTramo)
		{
			Print("[STRACK] suave tramo retroceso ignorado recibido=" + tramo.ToString() + " vigente=" + s_ServerTramo.ToString());
			return;
		}
		else
		{
			s_ServerCase = code;
			s_ServerTramo = tramo;
			s_ServerFin = false;
		}
		Print("[STRACK] case RPC code=" + code.ToString() + " tramo=" + tramo.ToString() + " fin=" + finInt.ToString());
		if ((tramo == 4 || finInt != 0) && player && GetGame() && GetGame().IsServer() && GetGame().IsMultiplayer() && player.GetIdentity())
		{
			ack = new ScriptRPC();
			ack.Write(tramo);
			ack.Write(finInt);
			ack.Send(player, STRACK_RPC_POT_ACK, true, player.GetIdentity());
			Print("[STRACK] suave parada ACK enviado tramo=" + tramo.ToString());
		}
		if (isNewRun && code == 2)
		{
			STRACK_Server.ResendPotId(player);
		}
	}

	static int ServerCase()
	{
		if (s_ServerCase != 0)
		{
			return s_ServerCase;
		}
		return s_LocalCase;
	}

	static bool ServerPotFrozen()
	{
		int tramo;
		bool fin;
		tramo = s_ServerTramo;
		fin = s_ServerFin;
		if (s_ServerCase == 0)
		{
			tramo = s_LocalTramo;
			fin = s_LocalFin;
		}
		if (fin)
		{
			return true;
		}
		if (tramo == 4)
		{
			return true;
		}
		return false;
	}

	static void OnCommand(PlayerBase player, float dt)
	{
		bool owner;
		if (dt > 0.0)
		{
			s_Dt = dt;
		}
		if (!player || !GetGame())
		{
			return;
		}
		owner = false;
		if (GetGame().GetPlayer() == player)
		{
			owner = true;
		}
		if (owner)
		{
			OwnerTick(player);
		}
		if (GetGame().IsServer())
		{
			ServerApply(player);
		}
	}

	static void ServerAfterMove(PlayerBase player)
	{
		if (!GetGame() || !GetGame().IsServer())
		{
			return;
		}
		ServerApply(player);
	}

	static void Read(PlayerBase player, ParamsReadContext ctx)
	{
		float speed;
		float angle;
		float aim;
		speed = 0.0;
		angle = 0.0;
		aim = 0.0;
		if (!ctx.Read(speed))
		{
			Print("[STRACK] move RPC lectura incompleta");
			return;
		}
		if (!ctx.Read(angle))
		{
			Print("[STRACK] move RPC lectura incompleta");
			return;
		}
		if (!ctx.Read(aim))
		{
			Print("[STRACK] move RPC lectura incompleta");
			return;
		}
		if (speed < 0.0)
		{
			s_ServerOn = false;
			if (player)
			{
				Release(player, s_RaiseServer);
				s_RaiseServer = false;
			}
			return;
		}
		s_ServerSpeed = speed;
		s_ServerAngle = angle;
		s_ServerAim = aim;
		s_ServerOn = true;
		s_ServerUntil = GetGame().GetTickTime() + 0.5;
	}

	protected static void OwnerTick(PlayerBase player)
	{
		HumanInputController hic;
		float now;
		float compass;
		float angle;
		float speed;
		float aim;
		float err;
		if (!s_Want)
		{
			return;
		}
		hic = player.GetInputController();
		if (!hic)
		{
			return;
		}
		now = GetGame().GetTickTime();
		compass = -hic.GetHeadingAngle() * Math.RAD2DEG;
		speed = 1.0;
		angle = 0.0;
		aim = 0.0;
		if ((s_Seg % 3) == 1)
		{
			if (!s_TurnInited)
			{
				s_Target = compass + 180.0;
				if (s_Target >= 360.0)
				{
					s_Target = s_Target - 360.0;
				}
				s_TurnInited = true;
				s_SegT0 = now;
				Print("[STRACK] move giro hacia " + s_Target.ToString());
			}
			// Turn in place: no walk, aim change toward the target heading
			// (OverrideAimChangeX, human.c:259), closed loop on the heading.
			speed = 0.0;
			err = Wrap180(s_Target - compass);
			aim = Math.Clamp(err * s_AimGain * (s_Dt * 60.0), -s_AimMax * (s_Dt * 60.0), s_AimMax * (s_Dt * 60.0));
			if (Math.AbsFloat(err) < 3.0 || (now - s_SegT0) >= 6.0)
			{
				Print("[STRACK] move giro fin rumbo=" + compass.ToString() + " objetivo=" + s_Target.ToString() + " t=" + (now - s_SegT0).ToString());
				aim = 0.0;
				Advance(now);
			}
		}
		else
		{
			if (s_NoWalk)
			{
				speed = 0.0;
				if ((now - s_SegT0) >= 1.0)
				{
					Advance(now);
				}
			}
			else if ((now - s_SegT0) >= 3.0)
			{
				Advance(now);
			}
		}
		if (!s_Want)
		{
			Release(player, s_RaiseOwner);
			s_RaiseOwner = false;
			Send(-1.0, 0.0, 0.0);
			return;
		}
		hic.OverrideMovementSpeed(HumanInputControllerOverrideType.ENABLED, speed);
		hic.OverrideMovementAngle(HumanInputControllerOverrideType.ENABLED, angle);
		hic.OverrideAimChangeX(HumanInputControllerOverrideType.ENABLED, aim);
		hic.OverrideRaise(HumanInputControllerOverrideType.ENABLED, false);
		s_RaiseOwner = true;
		Send(speed, angle, aim);
	}

	protected static void Advance(float now)
	{
		s_Seg = s_Seg + 1;
		s_SegT0 = now;
		s_TurnInited = false;
		if (s_Seg >= 9)
		{
			s_Want = false;
			Print("[STRACK] move self termino 3 tandas");
		}
	}

	protected static void ServerApply(PlayerBase player)
	{
		HumanInputController hic;
		if (!s_ServerOn)
		{
			return;
		}
		if (GetGame().GetTickTime() > s_ServerUntil)
		{
			s_ServerOn = false;
			Release(player, s_RaiseServer);
			s_RaiseServer = false;
			return;
		}
		hic = player.GetInputController();
		if (!hic)
		{
			return;
		}
		hic.OverrideMovementSpeed(HumanInputControllerOverrideType.ENABLED, s_ServerSpeed);
		hic.OverrideMovementAngle(HumanInputControllerOverrideType.ENABLED, s_ServerAngle);
		hic.OverrideAimChangeX(HumanInputControllerOverrideType.ENABLED, s_ServerAim);
		hic.OverrideRaise(HumanInputControllerOverrideType.ENABLED, false);
		s_RaiseServer = true;
	}

	protected static void Release(PlayerBase player, bool raised)
	{
		HumanInputController hic;
		hic = player.GetInputController();
		if (!hic)
		{
			return;
		}
		hic.OverrideMovementSpeed(HumanInputControllerOverrideType.DISABLED, 0.0);
		hic.OverrideMovementAngle(HumanInputControllerOverrideType.DISABLED, 0.0);
		hic.OverrideAimChangeX(HumanInputControllerOverrideType.DISABLED, 0.0);
		if (raised)
		{
			hic.OverrideRaise(HumanInputControllerOverrideType.DISABLED, false);
		}
	}

	protected static void Send(float speed, float angle, float aim)
	{
		ScriptInputUserData message;
		if (!GetGame() || !GetGame().IsMultiplayer() || !GetGame().IsClient())
		{
			return;
		}
		if (!ScriptInputUserData.CanStoreInputUserData())
		{
			return;
		}
		message = new ScriptInputUserData();
		message.Write(STRACK_UDT_MOVE);
		message.Write(speed);
		message.Write(angle);
		message.Write(aim);
		message.Send();
	}

	protected static float Wrap180(float angle)
	{
		float wrapped;
		wrapped = angle;
		while (wrapped > 180.0)
		{
			wrapped = wrapped - 360.0;
		}
		while (wrapped < -180.0)
		{
			wrapped = wrapped + 360.0;
		}
		return wrapped;
	}
};

modded class PlayerBase
{
	override bool OnInputUserDataProcess(int userDataType, ParamsReadContext ctx)
	{
		if (userDataType == STRACK_UDT_MOVE)
		{
			STRACK_Move.Read(this, ctx);
			return true;
		}
		if (userDataType == STRACK_UDT_CASE)
		{
			STRACK_Move.ReadCase(this, ctx);
			return true;
		}
		return super.OnInputUserDataProcess(userDataType, ctx);
	}

	override void CommandHandler(float pDt, int pCurrentCommandID, bool pCurrentCommandFinished)
	{
		super.CommandHandler(pDt, pCurrentCommandID, pCurrentCommandFinished);
		STRACK_Move.OnCommand(this, pDt);
	}

	protected override event void ConsumeMove(PawnMove pMove)
	{
		super.ConsumeMove(pMove);
		STRACK_Move.ServerAfterMove(this);
	}
};
