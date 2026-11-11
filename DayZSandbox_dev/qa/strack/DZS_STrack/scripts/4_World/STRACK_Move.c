// Optional -strack_move=self. Owner and server both apply
// OverrideMovementSpeed / OverrideMovementAngle (human.c:253-256), same split
// as MCP_PlayerMove: the owner's overrides alone do not walk a multiplayer pawn.
// Turn is a steered walk (speed 1, angle toward +180 compass), not a pure
// in-place animation: the override has no separate turn-in-place value.

const int STRACK_UDT_MOVE = 78541091;

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
	static float s_AimGain = 0.002;
	static float s_AimMax = 0.08;
	static float s_ServerUntil;

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

	static void OnCommand(PlayerBase player)
	{
		bool owner;
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
			aim = Math.Clamp(err * s_AimGain, -s_AimMax, s_AimMax);
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
		return super.OnInputUserDataProcess(userDataType, ctx);
	}

	override void CommandHandler(float pDt, int pCurrentCommandID, bool pCurrentCommandFinished)
	{
		super.CommandHandler(pDt, pCurrentCommandID, pCurrentCommandFinished);
		STRACK_Move.OnCommand(this);
	}

	protected override event void ConsumeMove(PawnMove pMove)
	{
		super.ConsumeMove(pMove);
		STRACK_Move.ServerAfterMove(this);
	}
};
