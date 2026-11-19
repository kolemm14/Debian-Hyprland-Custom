import { integer, text, sqliteTable, primaryKey, index } from "drizzle-orm/sqlite-core";
export const interactions = sqliteTable("interactions", {
 userId:text("user_id").notNull(), itemId:text("item_id").notNull(),
 favorite:integer("favorite").notNull().default(0), rating:integer("rating"), updatedAt:integer("updated_at").notNull(),
},t=>[primaryKey({columns:[t.userId,t.itemId]}),index("interactions_item").on(t.itemId)]);
export const events=sqliteTable("events",{
 userId:text("user_id").notNull(),itemId:text("item_id").notNull(),kind:text("kind").notNull(),day:text("day").notNull(),createdAt:integer("created_at").notNull(),
},t=>[primaryKey({columns:[t.userId,t.itemId,t.kind,t.day]}),index("events_item_day").on(t.itemId,t.day)]);
