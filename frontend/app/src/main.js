import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import './assets/tailwind.css';
import Toast, { POSITION } from 'vue-toastification';
import 'vue-toastification/dist/index.css';
import ElementPlus from "element-plus";
import "element-plus/dist/index.css";

const app = createApp(App);

// runtime compiler option for custom elements
app.config.compilerOptions = app.config.compilerOptions || {};
app.config.compilerOptions.isCustomElement = (tag) => tag === 'lord-icon' || tag.startsWith('lord-icon-');

// load lord-icon webcomponent
const lordScript = document.createElement('script');
lordScript.src = "https://cdn.lordicon.com/lusqsztk.js";
lordScript.async = true;
document.head.appendChild(lordScript);

app.use(ElementPlus);
app.use(Toast, {
  position: POSITION.TOP_LEFT,
  timeout: 5000,
  zIndex: 2147483647
});

app.config.devtools = true;

app.use(router).mount('#app');