class STRACK_Boot
{
	protected static bool s_Weather;
	protected static int s_Tries;

	static void ArmPlayer(PlayerBase player)
	{
		HumanInventory inv;
		EntityAI gun;
		if (!player || !GetGame() || !GetGame().IsServer())
		{
			return;
		}
		ApplyWorld();
		inv = player.GetHumanInventory();
		if (inv && !inv.GetEntityInHands())
		{
			gun = inv.CreateInHands("M4A1");
			if (gun)
			{
				Print("[STRACK] M4A1 en manos");
			}
			else
			{
				Print("[STRACK] CreateInHands M4A1 devolvio null");
			}
		}
		s_Tries = s_Tries + 1;
		if (s_Tries < 8 && inv && !inv.GetEntityInHands())
		{
			GetGame().GetCallQueue(CALL_CATEGORY_SYSTEM).CallLater(STRACK_Boot.ArmPlayer, 1000, false, player);
		}
	}

	protected static void ApplyWorld()
	{
		Weather weather;
		World world;
		if (s_Weather)
		{
			return;
		}
		s_Weather = true;
		world = GetGame().GetWorld();
		if (world)
		{
			world.SetDate(2026, 6, 15, 12, 0);
			Print("[STRACK] hora 12:00");
		}
		else
		{
			Print("[STRACK] GetWorld null");
		}
		weather = GetGame().GetWeather();
		if (!weather)
		{
			Print("[STRACK] GetWeather null");
			return;
		}
		weather.MissionWeather(true);
		weather.SetWeatherUpdateFreeze(true);
		weather.GetOvercast().Set(0.0, 0, 0);
		weather.GetRain().Set(0.0, 0, 0);
		weather.GetFog().Set(0.0, 0, 0);
		weather.GetSnowfall().Set(0.0, 0, 0);
		weather.SetWindSpeed(0.1);
		Print("[STRACK] clima despejado");
	}
};

modded class MissionServer
{
	override void InvokeOnConnect(PlayerBase player, PlayerIdentity identity)
	{
		super.InvokeOnConnect(player, identity);
		Print("[STRACK] jugador conectado");
		STRACK_Move.ServerMarkNewRun();
		STRACK_Boot.ArmPlayer(player);
	}

	override void OnUpdate(float timeslice)
	{
		super.OnUpdate(timeslice);
		STRACK_Server.TickSrv(timeslice);
	}
};

modded class MissionGameplay
{
	override void OnUpdate(float timeslice)
	{
		super.OnUpdate(timeslice);
		STRACK_Session.TickStatic(timeslice);
		// Orquestador 2026-11-11: sin foco, la primera actualizacion encola la pausa
		// (missiongameplay.c:296-298) y el menu tapa las capturas. Mientras corre la sonda, se cierra.
		if (STRACK_Session.Running() && IsPaused())
		{
			Continue();
			Print("[STRACK] menu de pausa cerrado");
		}
	}
};
