CREATE TABLE `community_orgs` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`name` text NOT NULL,
	`type` text DEFAULT 'ngo' NOT NULL,
	`capabilities` text,
	`contact_name` text,
	`contact_phone` text,
	`coverage_area` text,
	`mou_id` text,
	`status` text DEFAULT 'active' NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_community_orgs_org` ON `community_orgs` (`org_id`);--> statement-breakpoint
CREATE TABLE `equipment` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text,
	`name` text NOT NULL,
	`category` text DEFAULT 'general' NOT NULL,
	`status` text DEFAULT 'available' NOT NULL,
	`checked_out_by` text,
	`checked_out_at` integer,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_equipment_org` ON `equipment` (`org_id`);--> statement-breakpoint
CREATE TABLE `field_checkins` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`responder_id` text NOT NULL,
	`type` text NOT NULL,
	`location` text,
	`shift_id` text,
	`timestamp` integer NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_field_checkins_org` ON `field_checkins` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_field_checkins_responder` ON `field_checkins` (`responder_id`);--> statement-breakpoint
CREATE TABLE `field_reports` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`responder_id` text NOT NULL,
	`form_type` text NOT NULL,
	`task_id` text,
	`data` text,
	`attachments` text,
	`location` text,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_field_reports_org` ON `field_reports` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_field_reports_incident` ON `field_reports` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_field_reports_type` ON `field_reports` (`form_type`);--> statement-breakpoint
CREATE TABLE `help_requests` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text,
	`source` text DEFAULT 'public' NOT NULL,
	`external_id` text,
	`category` text DEFAULT 'other' NOT NULL,
	`description` text,
	`geo` text,
	`address` text,
	`contact_name` text,
	`contact_phone` text,
	`people_count` integer DEFAULT 1 NOT NULL,
	`priority` text DEFAULT 'medium' NOT NULL,
	`score` real DEFAULT 0 NOT NULL,
	`status` text DEFAULT 'pending' NOT NULL,
	`confidence` real DEFAULT 0.5 NOT NULL,
	`merged_into_id` text,
	`assigned_task_id` text,
	`repeat_caller` integer DEFAULT false NOT NULL,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_help_requests_org` ON `help_requests` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_help_requests_incident` ON `help_requests` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_help_requests_status` ON `help_requests` (`status`);--> statement-breakpoint
CREATE INDEX `idx_help_requests_source_ext` ON `help_requests` (`source`,`external_id`);--> statement-breakpoint
CREATE TABLE `responders` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text,
	`user_id` text,
	`name` text NOT NULL,
	`kind` text DEFAULT 'responder' NOT NULL,
	`status` text DEFAULT 'available' NOT NULL,
	`skills` text,
	`certifications` text,
	`contact_phone` text,
	`current_location` text,
	`team_id` text,
	`availability_start` integer,
	`availability_end` integer,
	`visibility` text DEFAULT 'internal' NOT NULL,
	`review_status` text DEFAULT 'draft' NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_responders_org` ON `responders` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_responders_incident` ON `responders` (`incident_id`);--> statement-breakpoint
CREATE INDEX `idx_responders_status` ON `responders` (`status`);--> statement-breakpoint
CREATE TABLE `shifts` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text NOT NULL,
	`responder_id` text NOT NULL,
	`team_id` text,
	`role` text,
	`start_time` integer NOT NULL,
	`end_time` integer,
	`buddy_id` text,
	`status` text DEFAULT 'scheduled' NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_shifts_org` ON `shifts` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_shifts_responder` ON `shifts` (`responder_id`);--> statement-breakpoint
CREATE TABLE `task_attachments` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`task_id` text NOT NULL,
	`r2_key` text NOT NULL,
	`name` text NOT NULL,
	`kind` text DEFAULT 'file' NOT NULL,
	`uploaded_by` text NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_task_attachments_task` ON `task_attachments` (`task_id`);--> statement-breakpoint
CREATE TABLE `task_comments` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`task_id` text NOT NULL,
	`author_id` text NOT NULL,
	`body` text NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_task_comments_task` ON `task_comments` (`task_id`);--> statement-breakpoint
CREATE TABLE `task_extras` (
	`task_id` text PRIMARY KEY NOT NULL,
	`kind` text DEFAULT 'general' NOT NULL,
	`geo` text,
	`assignee_user_id` text,
	`sla_at` integer,
	`parent_id` text,
	`dependencies` text,
	`risk_score` real DEFAULT 0 NOT NULL,
	`impact_score` real DEFAULT 0 NOT NULL,
	`urgency_score` real DEFAULT 0 NOT NULL,
	`public_visible` integer DEFAULT false NOT NULL,
	`checklist` text,
	`completion_proof` text,
	`verified_by` text,
	`verified_at` integer,
	`h3` text
);
--> statement-breakpoint
CREATE TABLE `task_links` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`task_id` text NOT NULL,
	`target_type` text NOT NULL,
	`target_id` text NOT NULL,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_task_links_task` ON `task_links` (`task_id`);--> statement-breakpoint
CREATE INDEX `idx_task_links_target` ON `task_links` (`target_type`,`target_id`);--> statement-breakpoint
CREATE TABLE `task_templates` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`name` text NOT NULL,
	`kind` text DEFAULT 'general' NOT NULL,
	`title` text NOT NULL,
	`description` text,
	`priority` text DEFAULT 'medium' NOT NULL,
	`checklist` text,
	`recurring_cron` text,
	`created_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `vehicles` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`incident_id` text,
	`name` text NOT NULL,
	`type` text DEFAULT 'truck' NOT NULL,
	`capacity` integer DEFAULT 4 NOT NULL,
	`status` text DEFAULT 'available' NOT NULL,
	`team_id` text,
	`fuel_level` integer,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_vehicles_org` ON `vehicles` (`org_id`);--> statement-breakpoint
CREATE TABLE `volunteer_profiles` (
	`id` text PRIMARY KEY NOT NULL,
	`org_id` text NOT NULL,
	`responder_id` text NOT NULL,
	`verification_status` text DEFAULT 'pending' NOT NULL,
	`training_status` text DEFAULT 'not_started' NOT NULL,
	`quiz_score` real,
	`background_status` text DEFAULT 'pending' NOT NULL,
	`minor_guardian_consent` integer,
	`insurance_flag` integer DEFAULT false NOT NULL,
	`safety_briefing` integer DEFAULT false NOT NULL,
	`total_hours` real DEFAULT 0 NOT NULL,
	`supervisor_id` text,
	`org_affiliation` text,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	FOREIGN KEY (`org_id`) REFERENCES `orgs`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE INDEX `idx_volunteer_profiles_org` ON `volunteer_profiles` (`org_id`);--> statement-breakpoint
CREATE INDEX `idx_volunteer_profiles_responder` ON `volunteer_profiles` (`responder_id`);