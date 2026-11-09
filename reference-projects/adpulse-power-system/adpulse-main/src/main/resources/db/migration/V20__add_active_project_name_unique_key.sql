ALTER TABLE pm_project
    ADD UNIQUE KEY uk_pm_project_name_deleted (project_name, deleted_at);
