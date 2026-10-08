const $ = id => document.getElementById(id);
const base = new URL('./', window.location.href);
const token = localStorage.getItem('ai_interviewer_token') || '';
const translations = {
  zh: {badge:'模拟面试',back:'返回正式面试',title:'先练习，再从容开始。',intro:'用一次完整问答，熟悉听题、作答和提交的节奏。',notice:'仅供体验 · 不计成绩 · 不保存面试记录',loginTitle:'请先登录学生账号',loginCopy:'登录后即可体验，无需绑定人脸照片。',login:'前往登录',prep:'开始前，检查一下设备',language:'面试语言',prepCopy:'共 6 道练习题。摄像头仅在本机预览；麦克风声音会发送给语音服务进行实时转写。无需人脸核验，不录制或上传完整录像。',consent:'我同意本次使用摄像头预览和麦克风实时语音识别。',check:'检测摄像头与麦克风',start:'开始模拟面试',interviewer:'模拟面试官',replay:'重听问题',yourAnswer:'本轮回答',record:'开始作答',finish:'回答完毕',next:'下一题',exit:'退出本次体验',preview:'摄像头本机预览 · 不保存',level:'麦克风音量',done:'体验完成',doneCopy:'你已熟悉面试流程。本次体验没有生成成绩，也没有保存面试记录。',again:'再练一次',footer:'练习题用于熟悉操作，不代表正式面试题目。离开页面后，本次进度不会保留。',deviceReady:'设备已就绪，可以开始模拟面试。',deviceError:'无法使用摄像头或麦克风，请检查浏览器权限和设备连接后重试。',consentFirst:'请先勾选设备与语音识别授权。',listening:'正在听你回答，请说话；完成后点击“回答完毕”。',connecting:'正在连接语音服务…',processing:'正在识别回答…',accepted:'回答已收到。点击“下一题”继续。',speaking:'正在播放问题…',speakRetry:'语音未能自动播放，请点击“重听问题”；也可以阅读题目后作答。',ready:'听完或读完题目后，点击“开始作答”。',network:'连接中断，请重新开始作答。',login_required:'登录已失效，请返回正式面试页面重新登录。',session_expired:'本次体验已结束或超时，请退出后重新开始。',already_active:'已有未结束的体验。请关闭原体验，或等待最长 20 分钟后重试。',rate_limit:'本小时体验次数已用完，请稍后再试。',capacity:'当前体验人数较多，请稍后重试。',asr_empty:'没有识别到回答，请靠近麦克风并重新作答。',asr_unavailable:'语音识别暂不可用，请稍后重新作答。',answer_timeout:'单次作答最长 2 分钟，请重新作答。',connection_timeout:'连接超时，请重新作答。',stale_turn:'题目状态已变化，请退出后重新开始。'},
  en: {badge:'Practice',back:'Back to interview',title:'Practice first. Begin with confidence.',intro:'Get comfortable with listening, answering, and moving to the next question.',notice:'Practice only · No grades · No interview records saved',loginTitle:'Sign in with your student account',loginCopy:'No enrolled face photo is required for practice.',login:'Go to sign in',prep:'A quick check before you begin',language:'Interview language',prepCopy:'Six practice questions. Camera video stays on your device. Microphone audio is sent to the speech service for live transcription. No face verification or full video recording.',consent:'I agree to camera preview and live microphone speech recognition for this practice.',check:'Check camera and microphone',start:'Start practice',interviewer:'Practice interviewer',replay:'Replay question',yourAnswer:'Your current answer',record:'Start answering',finish:'Finish answer',next:'Next question',exit:'Exit practice',preview:'Local camera preview · Not saved',level:'Microphone level',done:'Practice complete',doneCopy:'You have completed the experience. No grades or interview records were saved.',again:'Practice again',footer:'These questions are for practicing the process, not the official interview. Progress is not kept after you leave.',deviceReady:'Devices are ready. You can start practice.',deviceError:'Camera or microphone unavailable. Check browser permissions and devices, then retry.',consentFirst:'Please agree to camera and speech recognition use first.',listening:'Listening. Speak now, then click “Finish answer”.',connecting:'Connecting to speech recognition…',processing:'Recognizing your answer…',accepted:'Answer received. Click “Next question” to continue.',speaking:'Playing the question…',speakRetry:'Audio could not play. Click “Replay question”, or read the question and start answering.',ready:'After listening or reading, click “Start answering”.',network:'Connection interrupted. Please start your answer again.',login_required:'Your login expired. Return to the interview page and sign in again.',session_expired:'This practice ended or expired. Exit and start again.',already_active:'Another practice is still open. Exit it or wait up to 20 minutes and try again.',rate_limit:'Hourly practice limit reached. Please try again later.',capacity:'Practice is busy. Please try again shortly.',asr_empty:'No answer recognized. Move closer to the microphone and answer again.',asr_unavailable:'Speech recognition is unavailable. Please try again.',answer_timeout:'Each answer is limited to two minutes. Please answer again.',connection_timeout:'Connection timed out. Please answer again.',stale_turn:'The question state has changed. Exit and start again.'}
};
let lang='zh', stream=null, context=null, processor=null, source=null, silent=null, ws=null;
let session=null, pending=null, player=null, audioURL=null, speakingId=0, recording=false, questionComplete=false, busy=false, timer=null;
const t = key => translations[lang][key] || translations[lang].network;
function status(key,error=false){$('status').textContent=t(key);$('status').classList.toggle('error',error);}
function translate(){document.documentElement.lang=lang==='zh'?'zh-CN':'en';document.querySelectorAll('[data-t]').forEach(el=>el.textContent=t(el.dataset.t));}
function update(){
  $('start').disabled=busy||!stream||!$('consent').checked;
  $('check').disabled=busy;
  $('consent').disabled=busy;
  $('language').disabled=busy;
  $('record').disabled=busy||recording||questionComplete;
  $('finish').disabled=!recording||busy;
  $('replay').disabled=busy||recording||questionComplete;
}
async function request(path,options={}){
  const response=await fetch(new URL(path,base),{...options,headers:{Authorization:`Bearer ${token}`,...options.headers}});
  if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.code||'network');}
  return response;
}
function stopPlayback(){speakingId++; if(player){player.pause();player.src='';player=null;} if(audioURL){URL.revokeObjectURL(audioURL);audioURL=null;}}
function stopCapture(){
  recording=false;clearTimeout(timer);timer=null;
  if(processor){processor.onaudioprocess=null;processor.disconnect();processor=null;}
  if(source){source.disconnect();source=null;}if(silent){silent.disconnect();silent=null;}
  if(context){context.close().catch(()=>{});context=null;}$('level').value=0;
}
function stopDevices(){stopCapture();if(stream){stream.getTracks().forEach(track=>track.stop());stream=null;}$('video').srcObject=null;}
function closeSocket(){if(ws){ws.onclose=null;ws.onerror=null;ws.onmessage=null;ws.close();ws=null;}}
async function discard(){
  const sid=session?.session_id;
  session=null;pending=null;stopPlayback();stopDevices();closeSocket();busy=false;
  if(sid) await request(`api/sessions/${sid}`,{method:'DELETE',keepalive:true}).catch(()=>{});
}
async function play(){
  if(!session)return;
  stopPlayback(); const id=speakingId;busy=true;update();status('speaking');
  try{
    const response=await request(`api/sessions/${session.session_id}/audio`);
    const blob=await response.blob();if(id!==speakingId)return;
    audioURL=URL.createObjectURL(blob);player=new Audio(audioURL);
    const unlock=()=>{if(id===speakingId){busy=false;update();status('ready');}};
    player.onended=unlock;player.onerror=()=>{unlock();status('speakRetry',true);};
    await player.play();
  }catch(error){if(id===speakingId){busy=false;update();status(error.message==='login_required'?'login_required':'speakRetry',true);}}
}
function showQuestion(){
  questionComplete=false;pending=null;$('question').textContent=session.question;
  $('progress').textContent=`${session.turn+1} / ${session.total}`;$('transcript').textContent='';$('next').hidden=true;
  busy=false;update();play();
}
$('language').onchange=()=>{lang=$('language').value;translate();$('status').textContent='';};
$('consent').onchange=()=>{if(!$('consent').checked)stopDevices();update();};
$('check').onclick=async()=>{
  if(!$('consent').checked){status('consentFirst',true);return;}
  busy=true;update();stopDevices();
  try{stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:640},height:{ideal:480}},audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true}});$('video').srcObject=stream;status('deviceReady');}
  catch{status('deviceError',true);}finally{busy=false;update();}
};
$('start').onclick=async()=>{
  if(busy||!stream||!$('consent').checked)return;busy=true;update();
  try{session=await(await request('api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({language:lang})})).json();$('setup').hidden=true;$('experience').hidden=false;showQuestion();}
  catch(error){status(error.message,true);busy=false;update();}
};
function pcm16(input,rate){
  const ratio=rate/16000, output=new Int16Array(Math.floor(input.length/ratio));
  for(let i=0;i<output.length;i++){let sum=0,n=0;for(let j=Math.floor(i*ratio);j<Math.min(input.length,Math.floor((i+1)*ratio));j++){sum+=input[j];n++;}const value=Math.max(-1,Math.min(1,sum/(n||1)));output[i]=value<0?value*32768:value*32767;}return output;
}
async function startCapture(){
  const socket=ws, capture=new AudioContext();context=capture;await capture.resume();
  if(context!==capture||ws!==socket||!session||!stream){await capture.close().catch(()=>{});return;}
  source=context.createMediaStreamSource(stream);processor=context.createScriptProcessor(4096,1,1);silent=context.createGain();silent.gain.value=0;
  processor.onaudioprocess=event=>{if(!recording||ws?.readyState!==WebSocket.OPEN)return;const input=event.inputBuffer.getChannelData(0);let sum=0;for(const v of input)sum+=v*v;$('level').value=Math.min(1,Math.sqrt(sum/input.length)*5);if(ws.bufferedAmount>128000){fail('network');return;}ws.send(pcm16(input,context.sampleRate).buffer);};
  source.connect(processor);processor.connect(silent);silent.connect(context.destination);
  recording=true;busy=false;update();status('listening');timer=setTimeout(finishAnswer,110000);
}
function fail(code){stopCapture();closeSocket();busy=false;update();status(code,true);}
$('record').onclick=()=>{
  if(busy||recording||questionComplete||!session)return;
  stopPlayback();closeSocket();busy=true;update();status('connecting');$('transcript').textContent='';
  const url=new URL('api/ws',base);url.protocol=location.protocol==='https:'?'wss:':'ws:';ws=new WebSocket(url);
  timer=setTimeout(()=>fail('connection_timeout'),20000);
  ws.onopen=()=>ws.send(JSON.stringify({token,session_id:session.session_id,turn:session.turn}));
  ws.onerror=()=>fail('network');ws.onclose=()=>fail('network');
  ws.onmessage=async event=>{
    const data=JSON.parse(event.data);
    if(data.type==='ready'){clearTimeout(timer);try{await startCapture();}catch{fail('deviceError');}}
    else if(data.type==='partial')$('transcript').textContent=data.text;
    else if(data.type==='error')fail(data.code);
    else if(data.type==='answer'){
      stopCapture();closeSocket();busy=false;questionComplete=true;
      if(data.completed){await discard();$('experience').hidden=true;$('complete').hidden=false;$('transcript').textContent='';$('status').textContent='';}
      else{$('transcript').textContent=data.text;pending=data;$('next').hidden=false;status('accepted');update();}
    }
  };
};
function finishAnswer(){if(!recording||busy)return;stopCapture();busy=true;update();status('processing');if(ws?.readyState===WebSocket.OPEN){ws.send(JSON.stringify({action:'finish'}));timer=setTimeout(()=>fail('connection_timeout'),30000);}else fail('network');}
$('finish').onclick=finishAnswer;
$('next').onclick=()=>{if(pending){session={session_id:pending.session_id,turn:pending.turn,total:pending.total,question:pending.question};showQuestion();}};
$('replay').onclick=play;
async function reset(){await discard();questionComplete=false;$('experience').hidden=true;$('complete').hidden=true;$('setup').hidden=false;$('consent').checked=false;$('transcript').textContent='';$('status').textContent='';update();}
$('exit').onclick=reset;$('again').onclick=reset;
window.addEventListener('pagehide',()=>{discard();});
if(!token){$('setup').hidden=true;$('login').hidden=false;}
translate();update();
