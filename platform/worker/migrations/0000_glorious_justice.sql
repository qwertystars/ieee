CREATE TABLE `api_keys` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`prefix` text NOT NULL,
	`hash` text NOT NULL,
	`scopes` text,
	`last_used_at` integer,
	`created_at` integer NOT NULL,
	`revoked_at` integer,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_api_keys_prefix` ON `api_keys` (`prefix`);--> statement-breakpoint
CREATE INDEX `idx_api_keys_org` ON `api_keys` (`org_id`);--> statement-breakpoint
CREATE TABLE `devices` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`user_agent` text,
	`last_ip` text,
	`fingerprint` text,
	`last_seen_at` integer NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_devices_user` ON `devices` (`user_id`);--> statement-breakpoint
CREATE TABLE `sessions` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`device_id` text,
	`token_hash` text NOT NULL,
	`expires_at` integer NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`device_id`) REFERENCES `devices`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_sessions_user` ON `sessions` (`user_id`);--> statement-breakpoint
CREATE INDEX `idx_sessions_token` ON `sessions` (`token_hash`);--> statement-breakpoint
CREATE TABLE `events` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text,
	`actor` text NOT NULL,
	`action` text NOT NULL,
	`entity` text NOT NULL,
	`before` text,
	`after` text,
	`ts` integer NOT NULL,
	`prev_hash` text NOT NULL,
	`hash` text NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_events_org` ON `events` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_events_entity` ON `events` (`entity`,`org_id`);--> statement-breakpoint
CREATE INDEX `idx_events_ts` ON `events` (`ts`);--> statement-breakpoint
CREATE TABLE `geo_index` (
	`entity_type` text NOT NULL,
	`entity_id` text NOT NULL,
	`h3` text NOT NULL,
	`org_id` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_geo_index_h3` ON `geo_index` (`h3`,`entity_type`);--> statement-breakpoint
CREATE INDEX `idx_geo_index_entity` ON `geo_index` (`entity_type`,`entity_id`);--> statement-breakpoint
CREATE INDEX `idx_geo_index_org` ON `geo_index` (`org_id`);--> statement-breakpoint
CREATE TABLE `idempotency` (
	`id` text PRIMARY KEY NOT NULL,
	`source` text NOT NULL,
	`external_id` text NOT NULL,
	`result` text,
	`created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_idem_source_ext` ON `idempotency` (`source`,`external_id`);--> statement-breakpoint
CREATE TABLE `incidents` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`type` text NOT NULL,
	`severity` text NOT NULL,
	`status` text DEFAULT 'monitoring' NOT NULL,
	`title` text NOT NULL,
	`description` text,
	`geometry` text,
	`starts_at` integer,
	`expected_end` integer,
	`config` text,
	`declaration_level` text DEFAULT 'none' NOT NULL,
	`command_owner_id` text,
	`merged_into_id` text,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_incidents_org` ON `incidents` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_incidents_status` ON `incidents` (`status`);--> statement-breakpoint
CREATE TABLE `orgs` (
	`id` text PRIMARY KEY NOT NULL,
	`name` text NOT NULL,
	`slug` text NOT NULL,
	`kind` text DEFAULT 'tenant' NOT NULL,
	`branding` text,
	`settings` text,
	`data_region` text,
	`locked` integer DEFAULT false NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `orgs_slug_unique` ON `orgs` (`slug`);--> statement-breakpoint
CREATE TABLE `settings` (
	`id` text PRIMARY KEY NOT NULL,
	`scope` text NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text,
	`user_id` text,
	`key` text NOT NULL,
	`value` text,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_settings_scope` ON `settings` (`scope`,`org_id`,`key`);--> statement-breakpoint
CREATE TABLE `memberships` (
	`id` text PRIMARY KEY NOT NULL,
	`user_id` text NOT NULL,
	`org_id` text NOT NULL,
	`role_id` text NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`role_id`) REFERENCES `roles`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_memberships_user` ON `memberships` (`user_id`);--> statement-breakpoint
CREATE INDEX `idx_memberships_org` ON `memberships` (`org_id`);--> statement-breakpoint
CREATE TABLE `role_permissions` (
	`id` text PRIMARY KEY NOT NULL,
	`role_id` text NOT NULL,
	`action` text NOT NULL,
	`subject` text NOT NULL,
	FOREIGN KEY (`role_id`) REFERENCES `roles`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_role_perms_role` ON `role_permissions` (`role_id`);--> statement-breakpoint
CREATE TABLE `roles` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`name` text NOT NULL,
	`system` integer DEFAULT false NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_roles_org` ON `roles` (`org_id`);--> statement-breakpoint
CREATE TABLE `users` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`email` text NOT NULL,
	`name` text NOT NULL,
	`phone` text,
	`role` text NOT NULL,
	`status` text DEFAULT 'invited' NOT NULL,
	`password_hash` text,
	`last_login_at` integer,
	`mfa_secret` text,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_users_org` ON `users` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_users_email` ON `users` (`email`);