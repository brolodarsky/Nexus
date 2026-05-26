from engine.core.hitl_queue import add_transaction

def seed():
    add_transaction(
        agent_name="career",
        action_type="write_file",
        target_file="Vault/1. The Core/1.1. Philosophy & Personal North Star/To Do List.md",
        original_content="- [ ] existing task 1\n- [ ] existing task 2\n",
        proposed_content="- [ ] existing task 1\n- [ ] existing task 2\n- [ ] Apply for Senior Frontend Role at Vercel\n",
        reasoning='{"confidence": 0.95, "alternatives_considered": ["Add to Current Learning"], "decision": "User explicitly asked to apply for the Vercel role, so appending it to the To Do List."}'
    )
    print("Seed complete.")

if __name__ == "__main__":
    seed()
