CREATE TABLE `queue` (
 `id` text PRIMARY KEY NOT NULL,
 `request_key` text NOT NULL UNIQUE,
 `payload` text NOT NULL,
 `profile_hash` text NOT NULL,
 `ip_hash` text NOT NULL,
 `created` integer NOT NULL,
 `consent_version` text NOT NULL,
 `state` text DEFAULT 'pending' NOT NULL
);
--> statement-breakpoint
CREATE INDEX `queue_state_created` ON `queue` (`state`,`created`);
