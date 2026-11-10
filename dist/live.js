(() => {
 const form=document.querySelector('#application'),status=form.querySelector('.form-status'),submit=form.querySelector('[type="submit"]');
 const label=document.createElement('label');label.className='checkbox';
 label.innerHTML='<input type="checkbox" name="broadcastConsent" required><span>Разрешаю передать никнейм, ссылку Steam, игру, уровень, цель, расписание, часовой пояс и комментарий на хостинг Sites/Cloudflare, сохранить на ПК организатора и разослать всем подписчикам <a href="https://t.me/steamGam3rsbot" target="_blank" rel="noopener">Telegram-бота</a>. Получатели могут сохранить или переслать анкету. <button type="button" id="broadcast-details">Подробнее</button></span>';
 submit.before(label);
 document.querySelector('#broadcast-details').addEventListener('click',()=>document.querySelector('[data-doc="consent"]').click());
 docs.offer=['Условия сервиса — бета-версия','SteamGamers — бесплатный независимый проект для совершеннолетних пользователей. Мы принимаем анкеты для поиска напарников и рассылаем их добровольным подписчикам Telegram-бота. Подбор, ответы игроков и сроки доставки не гарантируются.','Отправляя анкету, указывайте только свои данные. Не размещайте пароли, коды доступа, телефон, адрес, платёжные данные или чужие контакты. Запрещены угрозы, травля, мошенничество и незаконный контент.','Анкеты автоматически отправляются всем активным подписчикам на момент получения заявки компьютером организатора. Если подписчиков нет, анкета сохраняется без рассылки. Автоматической модерации нет.','Это рабочая бета-версия. Юридические реквизиты оператора и окончательная оферта ещё не оформлены. Российская локализация всех данных не подтверждена. SteamGamers не связан с Valve.'];
 docs.privacy=['Как обрабатывается анкета','После отправки анкета сохраняется в закрытой базе хостинга Sites/Cloudflare. Бот на ПК организатора забирает её через HTTPS, сохраняет локально и отправляет подписчикам через Telegram. Секреты доступа и база не публикуются на странице.','Поля: никнейм, ссылка Steam, игра, уровень, цель, время, часовой пояс, добровольный комментарий. Цель — знакомство для совместной игры. Сервер также сохраняет время, версию согласия и хеши для ограничения повторных заявок; хостинг может вести технические журналы.','После подтверждённого сохранения на ПК содержимое анкеты удаляется из облачной очереди. При обращении бота удаляются облачные записи старше семи дней. Пока ПК выключен, очистка не выполняется. Локальная база очищается организатором вручную; автоматический срок удаления пока не настроен.','Анкету смогут прочитать все активные подписчики бота. Уже доставленные копии могут остаться у получателей и в Telegram. Удаление локальной записи не отзывает эти сообщения.','Юридические реквизиты оператора и полноценный канал обращений ещё не оформлены. Этот текст описывает фактическую работу бета-версии и не является подтверждением выполнения всех требований законодательства.'];
 docs.consent=['Согласие на передачу и рассылку анкеты','Отдельная отметка в форме разрешает передать перечисленные поля на хостинг Sites/Cloudflare, сохранить на ПК организатора и разослать активным подписчикам Telegram-бота @steamGam3rsbot. Цель — поиск друзей и напарников для игр.','Передаются никнейм, публичная ссылка Steam, игра, уровень, цель, расписание, часовой пояс и добровольный комментарий. Получатели могут сохранить или переслать анкету. Не указывайте сведения, которые не готовы раскрыть подписчикам.','Рассылка начинается после того, как ПК организатора заберёт очередь. Отмена получения анкет подписчиком: /stop в боте; удаление его chat_id из локальной базы: /delete_me. Эти команды не удаляют ранее отправленные анкеты автора.','Редакция: telegram-queue-v1. Юридические реквизиты и окончательные документы для промышленного запуска ещё требуют оформления.'];
 let pending=null,busy=false;
 form.addEventListener('submit',async event=>{
  event.preventDefault();event.stopImmediatePropagation();if(busy||!form.reportValidity())return;
  const values=Object.fromEntries(new FormData(form)),field=form.querySelector('[name="steam"]');
  if(!/^https:\/\/steamcommunity\.com\/(?:id\/[A-Za-z0-9_-]+|profiles\/\d{17})\/?$/.test(values.steam.trim())){field.setCustomValidity('Укажи публичную ссылку https://steamcommunity.com/id/nickname или /profiles/76561198000000000');field.reportValidity();return;}
  const data={};for(const key of Object.keys(labels))data[key]=(values[key]||'').trim();
  if(data.game==='Другая игра')data.game=values.customGame.trim();
  Object.assign(data,{consent:values.consent==='on',adult:values.consent==='on',broadcastConsent:values.broadcastConsent==='on',consentVersion:'telegram-queue-v1'});
  const fingerprint=JSON.stringify(data);if(!pending||pending.fingerprint!==fingerprint)pending={fingerprint,key:crypto.randomUUID()};
  busy=true;submit.disabled=true;submit.textContent='Отправляем…';status.textContent='Сохраняем заявку в очереди…';
  try{
   const response=await fetch('/api/applications',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':pending.key},body:fingerprint,signal:AbortSignal.timeout(20000)});
   let result;try{result=await response.json();}catch{throw new Error('Не удалось подтвердить сохранение. Повторите с теми же данными.');}
   if(response.status!==201)throw new Error(result.error||'Не удалось сохранить заявку. Повторите позже.');
   status.textContent='Заявка № '+result.id+' сохранена. Рассылка начнётся, когда бот на ПК заберёт очередь. Доставка пока не подтверждена.';
   last=Object.fromEntries(Object.keys(labels).map(k=>[k,data[k]||'Не указано']));
   const list=document.querySelector('#summary');list.replaceChildren();for(const [key,value] of Object.entries(last)){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=labels[key];dd.textContent=value;list.append(dt,dd);}
   document.querySelector('#result h2').textContent='Заявка сохранена.';
   document.querySelector('#result p').textContent='Номер: '+result.id+'. Анкета находится в очереди для бота. Это ещё не подтверждение доставки подписчикам.';
   document.querySelector('#result').showModal();
  }catch(error){status.textContent=error.name==='TimeoutError'?'Сервер не ответил вовремя. Данные остались в форме; повторите отправку, чтобы проверить сохранение.':(error.message==='Failed to fetch'?'Нет связи с сервером. Данные остались в форме. Повторите позже.':error.message);}
  finally{busy=false;submit.disabled=false;submit.innerHTML='Отправить заявку <span>↗</span>';}
 },true);
})();
