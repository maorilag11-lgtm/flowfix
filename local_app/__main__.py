from local_app.diagnostic_contract import module_choices
"""Launch with python3 -m local_app; loopback only, standard library."""
import argparse
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from .service import Sessions, Invalid, Conflict

STATIC=Path(__file__).parent/'static'
MAX_BODY=1500000
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass # Never log user input, URLs or payloads.
    def reply(self,status,data,mime='application/json; charset=utf-8'):
        body=json.dumps(data,ensure_ascii=False).encode() if mime.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers();self.wfile.write(body)
    def valid_host(self):return self.headers.get('Host') in self.server.hosts
    def setup(self):
        super().setup()
        self.connection.settimeout(20)
    def do_GET(self):
        if not self.valid_host():return self.reply(403,{'error':'Origine refusée.'})
        path=urlsplit(self.path).path
        try:
            if path=='/api/config':return self.reply(200,{'csrf':self.server.token})
            if path.startswith('/api/sessions/') and path.endswith('/export') and len(path.split('/'))==5:return self.reply(200,self.server.sessions.export_report(path.split('/')[3]))
            if path=='/api/settings':return self.reply(200,self.server.sessions.settings())
            if path=='/api/sessions':return self.reply(200,self.server.sessions.list())
            if path.startswith('/api/sessions/') and len(path.split('/'))==4:return self.reply(200,self.server.sessions.get(path.split('/')[-1]))
            files={'/trace-examples.json':('trace-examples.json','application/json; charset=utf-8'),'/root-trace.js':('root-trace.js','text/javascript; charset=utf-8'),'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if path in files:
                filename,mime=files[path];data=(STATIC/filename).read_bytes();return self.reply(200,json.loads(data) if mime.startswith('application/json') else data,mime)
            return self.reply(404,{'error':'Ressource introuvable.'})
        except KeyError:return self.reply(404,{'error':'Session introuvable.'})
        except Exception:return self.reply(500,{'error':'Lecture impossible. Vérifiez le stockage local.'})
    def do_POST(self):
        origin=self.headers.get('Origin')
        if not self.valid_host() or self.headers.get('X-FlowFix-Token')!=self.server.token or (origin and origin not in {'http://'+h for h in self.server.hosts}):
            return self.reply(403,{'error':'Origine refusée. Rechargez la page.'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>MAX_BODY:return self.reply(413,{'error':'La requête dépasse la limite de 1,5 Mo.'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.reply(415,{'error':'Format JSON requis.'})
            from flowfix.step1_intake.intake.trace_contract import decode_request
            body=decode_request(self.rfile.read(size))
            if not isinstance(body,dict):raise Invalid('Requête invalide.')
            parts=urlsplit(self.path).path.strip('/').split('/')
            if parts==['api','blueprint']:
                from .service import intake,text
                problem=intake({'blueprint':text(body.get('blueprint',''),1000000)},'preview')
                return self.reply(200,{'modules':module_choices(problem)})
            if parts==['api','settings']:return self.reply(200,self.server.sessions.settings(body))
            if parts==['api','sessions']:return self.reply(201,self.server.sessions.create(body))
            if len(parts)==4 and parts[:2]==['api','sessions'] and parts[3] in ['answer','feedback','delete','edit']:
                return self.reply(200,self.server.sessions.change(parts[2],body,parts[3]))
            return self.reply(404,{'error':'Action introuvable.'})
        except Conflict as exc:return self.reply(409,{'error':str(exc)})
        except KeyError:return self.reply(404,{'error':'Session introuvable.'})
        except Invalid as exc:return self.reply(400,{'error':str(exc)})
        except (ValueError,TypeError,RecursionError):return self.reply(400,{'error':'Données invalides : vérifiez les champs et le Blueprint JSON.'})
        except Exception:return self.reply(500,{'error':'Analyse impossible. Vos modifications n’ont pas été enregistrées.'})

def make_server(port,directory):
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.hosts={f'127.0.0.1:{server.server_port}',f'localhost:{server.server_port}'}
    server.token=secrets.token_urlsafe(32);server.sessions=Sessions(directory)
    return server

def main():
    parser=argparse.ArgumentParser(description='FlowFix MVP local')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir',default=str(Path(__file__).resolve().parents[1]/'.flowfix-data'))
    args=parser.parse_args();os.umask(0o077)
    server=make_server(args.port,args.data_dir)
    print(f'FlowFix : http://127.0.0.1:{server.server_port}\nSessions : {Path(args.data_dir).resolve()}\nCtrl+C pour arrêter.',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
