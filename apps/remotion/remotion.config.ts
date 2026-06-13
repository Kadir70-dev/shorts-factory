import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setCodec("h264");
// data/ is mounted here so staticFile() can read VO/music/assets
Config.setPublicDir("../../data");
