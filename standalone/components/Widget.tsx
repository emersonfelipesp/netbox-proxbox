'use client'

import { Notification } from '/components/Notification'
import { Rocket, Check, X, ArrowRight } from 'lucide-react'


export default function Widget () {
    return (
        <>
            <div className="bg-zinc-300 font-medium dark:bg-zinc-950 px-5 py-2 text-sm text-zinc-500 dark:text-zinc-400">
                Recentes
            </div>   
            <div className="divide-y-2 divide-zinc-300 dark:divide-zinc-950">
                <Notification.Root>
                    <Notification.Icon icon={Rocket} />
                    <Notification.Content text="Você foi convidado para participar de um projeto." />
                </Notification.Root>
                <Notification.Root>
                    <Notification.Content text="Você recebeu um convite para fazer parte da empresa Rocketseat." />
                    <Notification.Actions>
                        <Notification.Action onClick={() => {}} icon={X} />
                        <Notification.Action onClick={() => {}} icon={Check} className="bg-violet-500 hover:bg-violet-600 dark:bg-violet-500 dark:hover:bg-violet-600"/>
                    </Notification.Actions>
                </Notification.Root>
                <Notification.Root>
                    <Notification.Icon icon={Rocket} />
                    <Notification.Content text="Você foi convidado para participar de um projeto." />
                    <Notification.Actions>
                        <Notification.Action onClick={() => {}} icon={ArrowRight} className="bg-emerald-500 dark:bg-emerald-500" />
                    </Notification.Actions>
                </Notification.Root>
            </div>
        </>
    )
}