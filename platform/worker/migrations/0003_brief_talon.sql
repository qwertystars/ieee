CREATE TABLE `alerts` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`alert_type` text NOT NULL,
	`title` text NOT NULL,
	`message` text,
	`area` text,
	`severity` text DEFAULT 'warning' NOT NULL,
	`recommended_action` text,
	`confidence_score` real DEFAULT 0.5 NOT NULL,
	`acknowledged` integer DEFAULT false NOT NULL,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_alerts_org` ON `alerts` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_alerts_incident` ON `alerts` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_alerts_severity` ON `alerts` (`severity`);--> statement-breakpoint
CREATE TABLE `area_assessments` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`area_name` text NOT NULL,
	`geometry` text NOT NULL,
	`hazard_score` real DEFAULT 0 NOT NULL,
	`exposure_score` real DEFAULT 0 NOT NULL,
	`access_score` real DEFAULT 0 NOT NULL,
	`infrastructure_score` real DEFAULT 0 NOT NULL,
	`vulnerability_score` real DEFAULT 0 NOT NULL,
	`trend_score` real DEFAULT 0 NOT NULL,
	`report_score` real DEFAULT 0 NOT NULL,
	`overall_priority_score` real DEFAULT 0 NOT NULL,
	`priority_level` text DEFAULT 'unknown' NOT NULL,
	`summary` text,
	`components` text,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`updated_at` integer NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_area_assessments_org` ON `area_assessments` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_area_assessments_incident` ON `area_assessments` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_area_assessments_priority` ON `area_assessments` (`priority_level`);--> statement-breakpoint
CREATE TABLE `disaster_events` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`name` text NOT NULL,
	`type` text NOT NULL,
	`status` text DEFAULT 'active' NOT NULL,
	`description` text,
	`affected_region` text,
	`starts_at` integer,
	`expected_end` integer,
	`created_by` text,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_disaster_events_org` ON `disaster_events` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_disaster_events_incident` ON `disaster_events` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_disaster_events_status` ON `disaster_events` (`status`);--> statement-breakpoint
CREATE TABLE `incident_reports` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`reporter_type` text NOT NULL,
	`report_category` text NOT NULL,
	`description` text,
	`geometry` text NOT NULL,
	`photo_url` text,
	`urgency` text DEFAULT 'medium' NOT NULL,
	`verification_status` text DEFAULT 'unverified' NOT NULL,
	`confidence_score` real DEFAULT 0.5 NOT NULL,
	`pii_redacted_text` text,
	`cluster_id` text,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_incident_reports_org` ON `incident_reports` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_incident_reports_incident` ON `incident_reports` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_incident_reports_category` ON `incident_reports` (`report_category`);--> statement-breakpoint
CREATE TABLE `recommendations` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`area_assessment_id` text,
	`recommendation_type` text NOT NULL,
	`title` text NOT NULL,
	`description` text,
	`reasoning` text,
	`supporting_data` text,
	`confidence_score` real DEFAULT 0.5 NOT NULL,
	`urgency` text DEFAULT 'medium' NOT NULL,
	`status` text DEFAULT 'draft' NOT NULL,
	`assigned_to` text,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_recommendations_org` ON `recommendations` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_recommendations_incident` ON `recommendations` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_recommendations_status` ON `recommendations` (`status`);--> statement-breakpoint
CREATE TABLE `response_teams` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`name` text NOT NULL,
	`team_type` text NOT NULL,
	`current_location` text,
	`status` text DEFAULT 'available' NOT NULL,
	`capacity` integer DEFAULT 4 NOT NULL,
	`assigned_task_id` text,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`updated_at` integer NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_response_teams_org` ON `response_teams` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_response_teams_incident` ON `response_teams` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_response_teams_status` ON `response_teams` (`status`);--> statement-breakpoint
CREATE TABLE `road_statuses` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`road_name` text NOT NULL,
	`geometry` text NOT NULL,
	`status` text DEFAULT 'unknown' NOT NULL,
	`reason` text,
	`confidence_score` real DEFAULT 0.5 NOT NULL,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`updated_at` integer NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_road_statuses_org` ON `road_statuses` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_road_statuses_incident` ON `road_statuses` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_road_statuses_status` ON `road_statuses` (`status`);--> statement-breakpoint
CREATE TABLE `shelters` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`name` text NOT NULL,
	`geometry` text NOT NULL,
	`total_capacity` integer DEFAULT 0 NOT NULL,
	`current_occupancy` integer DEFAULT 0 NOT NULL,
	`food_status` text DEFAULT 'unknown' NOT NULL,
	`water_status` text DEFAULT 'unknown' NOT NULL,
	`medical_support` integer DEFAULT false NOT NULL,
	`accessibility_support` integer DEFAULT false NOT NULL,
	`status` text DEFAULT 'preparing' NOT NULL,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`updated_at` integer NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_shelters_org` ON `shelters` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_shelters_incident` ON `shelters` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_shelters_status` ON `shelters` (`status`);--> statement-breakpoint
CREATE TABLE `tasks` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`recommendation_id` text,
	`assigned_team_id` text,
	`title` text NOT NULL,
	`description` text,
	`location` text,
	`priority` text DEFAULT 'medium' NOT NULL,
	`status` text DEFAULT 'assigned' NOT NULL,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_tasks_org` ON `tasks` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_tasks_incident` ON `tasks` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_tasks_team` ON `tasks` (`assigned_team_id`);--> statement-breakpoint
CREATE INDEX `idx_tasks_status` ON `tasks` (`status`);