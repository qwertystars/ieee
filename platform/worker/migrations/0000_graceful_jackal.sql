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
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action,
	FOREIGN KEY (`incident_id`) REFERENCES `incidents`(`id`) ON UPDATE no action ON DELETE no action
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
CREATE UNIQUE INDEX `orgs_slug_unique` ON `orgs` (`slug`);