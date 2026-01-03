-- migrate_add_preferred_areas.sql
-- 用途：为 users 表添加 preferred_areas(JSON) 字段
-- 执行方式（MySQL 客户端）：
--   USE weather_aqi;
--   SOURCE migrate_add_preferred_areas.sql;

ALTER TABLE users
  ADD COLUMN preferred_areas JSON NULL AFTER created_at;

