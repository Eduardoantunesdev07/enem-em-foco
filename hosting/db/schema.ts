import { sqliteTable, text, integer, primaryKey, index } from "drizzle-orm/sqlite-core";

export const attempts = sqliteTable("attempts", {
  id: text("id").primaryKey(),
  owner: text("owner").notNull(),
  examId: integer("exam_id").notNull(),
  language: text("language").notNull(),
  createdAt: text("created_at").notNull(),
  submittedAt: text("submitted_at"),
  status: text("status").notNull(),
}, table => [index("attempts_owner_idx").on(table.owner)]);

export const answers = sqliteTable("answers", {
  attemptId: text("attempt_id").notNull().references(() => attempts.id),
  questionId: integer("question_id").notNull(),
  selectedOption: text("selected_option").notNull(),
  updatedAt: text("updated_at").notNull(),
}, table => [primaryKey({ columns: [table.attemptId, table.questionId] })]);

export const errorNotes = sqliteTable("error_notes", {
  owner: text("owner").notNull(),
  questionId: integer("question_id").notNull(),
  reason: text("reason").notNull(),
  note: text("note").notNull(),
  updatedAt: text("updated_at").notNull(),
}, table => [primaryKey({ columns: [table.owner, table.questionId] })]);
