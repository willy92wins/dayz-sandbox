class CfgPatches
{
	class DZS_STrack
	{
		units[] = {};
		weapons[] = {};
		requiredVersion = 0.1;
		requiredAddons[] = {"DZ_Data", "DZ_Scripts"};
	};
};

class CfgMods
{
	class DZS_STrack
	{
		dir = "DZS_STrack";
		name = "DZS_STrack";
		type = "mod";
		hideName = 1;
		hidePicture = 1;
		dependencies[] = {"Game", "World", "Mission"};
		class defs
		{
			class gameScriptModule
			{
				value = "";
				files[] = {"DZS_STrack/scripts/3_Game"};
			};
			class worldScriptModule
			{
				value = "";
				files[] = {"DZS_STrack/scripts/4_World"};
			};
			class missionScriptModule
			{
				value = "";
				files[] = {"DZS_STrack/scripts/5_Mission"};
			};
		};
	};
};
