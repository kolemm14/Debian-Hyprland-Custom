CREATE TABLE `events` (
	`user_id` text NOT NULL,
	`item_id` text NOT NULL,
	`kind` text NOT NULL,
	`day` text NOT NULL,
	`created_at` integer NOT NULL,
	PRIMARY KEY(`user_id`, `item_id`, `kind`, `day`)
);
--> statement-breakpoint
CREATE INDEX `events_item_day` ON `events` (`item_id`,`day`);--> statement-breakpoint
CREATE TABLE `interactions` (
	`user_id` text NOT NULL,
	`item_id` text NOT NULL,
	`favorite` integer DEFAULT 0 NOT NULL,
	`rating` integer,
	`updated_at` integer NOT NULL,
	PRIMARY KEY(`user_id`, `item_id`)
);
--> statement-breakpoint
CREATE INDEX `interactions_item` ON `interactions` (`item_id`);