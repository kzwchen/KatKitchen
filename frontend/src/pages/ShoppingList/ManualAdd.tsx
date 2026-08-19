import { useState } from 'react'
import { addListItem } from '../../api/client'
import { keys, useInvalidatingMutation } from '../../api/hooks'
import { useToast } from '../../components/Toast'

export function ManualAdd({ listId, planId }: { listId: number; planId: number }) {
  const [name, setName] = useState('')
  const toast = useToast()
  const add = useInvalidatingMutation(
    (customName: string) => addListItem(listId, { custom_name: customName }),
    [keys.list(planId), keys.suggestions(listId)],
  )

  return (
    <form
      className="manual-add"
      onSubmit={async (event) => {
        event.preventDefault()
        if (!name.trim()) return
        try {
          await add.mutateAsync(name.trim())
          setName('')
        } catch (error) {
          toast.showError(error)
        }
      }}
    >
      <input
        placeholder="Add something not from a recipe"
        value={name}
        onChange={(e) => setName(e.target.value)}
        aria-label="Add an item"
      />
      <button type="submit">Add</button>
    </form>
  )
}
