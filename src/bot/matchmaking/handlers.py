@matchmaking_router.callback_query(
    MatchCallback.filter(F.action == "start_communication"),
    StateFilter(UserStates.idle)
)
async def process_start_communication(
    callback: CallbackQuery,
    callback_data: MatchCallback,
    session: AsyncSession,
    state: FSMContext,
    bot: Bot,
):
    match_id = int(callback_data.match_id)
    user_id = callback.from_user.id

    match = await session.get(Match, match_id)
    if not match:
        await callback.message.answer("Match not found!")
        return

    comm_request = await session.scalar(
        select(CommunicationRequest).where(
            CommunicationRequest.match_id == match_id
        )
    )

    if comm_request:
        # Первый участник уже инициировал — второй вступает!
        if comm_request.initiator_id == user_id:
            await callback.message.answer("A chat invitation is already pending. Please wait for the other person to join.")
            return

        if (
            comm_request.receiver_id == user_id 
            and comm_request.status == CommunicationRequestStatus.PENDING
        ):
            comm_request.status = CommunicationRequestStatus.ACTIVE
            await session.commit()

            initiator_id = comm_request.initiator_id
            receiver_id = comm_request.receiver_id

            # Сгенерируйте или получите пригласительную ссылку (ВАЖНО: замените на свой вызов если нужно)
            invite_link = await get_or_create_communicator_invite(initiator_id, receiver_id)

            await bot.send_message(initiator_id, f"Your chat is ready! Here is your invite:\n{invite_link}")
            await bot.send_message(receiver_id, f"Your chat is ready! Here is your invite:\n{invite_link}")
            await callback.message.answer("Invite sent! Please check your messages.")
            return
        else:
            await callback.message.answer("This chat invitation is no longer valid or already active.")
            return

    # Чат ещё не был создан — создаём новый запрос
    if match.user1_id == user_id:
        initiator_id = user_id
        receiver_id = match.user2_id
    else:
        initiator_id = user_id
        receiver_id = match.user1_id

    new_request = CommunicationRequest(
        match_id=match_id,
        initiator_id=initiator_id,
        receiver_id=receiver_id,
        status=CommunicationRequestStatus.PENDING
    )
    session.add(new_request)
    await session.commit()
    await callback.message.answer("A chat invitation is already pending. Please wait for the other person to join.")
