"""Join the map and existing local migration histories without changing either."""

revision = "0047_merge_map_reconstruction"
down_revision = ("0046_agent_evaluation_cases", "0046_custom_map_points")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
