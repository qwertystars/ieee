CREATE TABLE `idempotency` (
	`id` text PRIMARY KEY NOT NULL,
	`source` text NOT NULL,
	`external_id` text NOT NULL,
	`result` text,
	`created_at` integer NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_idem_source_ext` ON `idempotency` (`source`,`external_id`);