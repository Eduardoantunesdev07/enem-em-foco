CREATE TABLE `answers` (
	`attempt_id` text NOT NULL,
	`question_id` integer NOT NULL,
	`selected_option` text NOT NULL,
	`updated_at` text NOT NULL,
	PRIMARY KEY(`attempt_id`, `question_id`),
	FOREIGN KEY (`attempt_id`) REFERENCES `attempts`(`id`) ON UPDATE no action ON DELETE no action
);
--> statement-breakpoint
CREATE TABLE `attempts` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`exam_id` integer NOT NULL,
	`language` text NOT NULL,
	`created_at` text NOT NULL,
	`submitted_at` text,
	`status` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `attempts_owner_idx` ON `attempts` (`owner`);--> statement-breakpoint
CREATE TABLE `error_notes` (
	`owner` text NOT NULL,
	`question_id` integer NOT NULL,
	`reason` text NOT NULL,
	`note` text NOT NULL,
	`updated_at` text NOT NULL,
	PRIMARY KEY(`owner`, `question_id`)
);
