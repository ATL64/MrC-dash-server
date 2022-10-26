from google.oauth2 import service_account
import dash
from dash.dependencies import Input, Output, State
import dash_core_components as dcc
import dash_html_components as html
import dash_table
import flask
from flask import request
import dash_bootstrap_components as dbc
import base64
import requests
import json
import pandas as pd
import pandas_gbq
import keyword_extractor.keyword_extractor as ky
from google.cloud import storage
import uuid
from datetime import datetime as dt
from datetime import date
import time
import math
import psycopg2


credentials_path = "/app/creds.json"

credentials = service_account.Credentials.from_service_account_file(
    credentials_path,
)

pandas_gbq.context.credentials = credentials
pandas_gbq.context.project = "xxxxxx"


# Style the button: http://dash-bootstrap-components.opensource.faculty.ai/l/components/button



app = flask.Flask(__name__)
dash_app = dash.Dash(__name__, server = app, url_base_pathname='/') #, external_stylesheets=[external_style]) #dbc.themes.DARKLY

dash_app.index_string = """<!DOCTYPE html>
<html>
    <head>
            <!-- Global site tag (gtag.js) - Google Analytics -->
            <script async src="https://www.googletagmanager.com/gtag/js?id=UA-165584893-1"></script>
            <script>
              window.dataLayer = window.dataLayer || [];
              function gtag(){dataLayer.push(arguments);}
              gtag('js', new Date());
            
              gtag('config', '----------------YOUR_GA_ID_HERE--------------');
            </script>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>"""

# Images/logos
image_filename_1 = 'logo_mr_c.png' # replace with your own image
encoded_image_1 = base64.b64encode(open(image_filename_1, 'rb').read())


# Serve local css
dash_app.css.config.serve_locally = True
dash_app.scripts.config.serve_locally = True



#####################
####### STYLES ######
#####################

tabs_styles = {
    'height': '60px',
    'width': '1100px',
    'marginLeft': 20
}
tab_style = {
    'borderBottom': '1px solid #333333',
    'padding': '20px',
    'backgroundColor': '#595959',
    'fontColor': 'black',
    'font-family': 'Courier New, monospace',
    'text-align': 'center',
    'text-vertical-align': 'center',
    'font-size': '120%',
    'width': '300px',
    'marginLeft': 40
}

tab_selected_style = {
    'borderTop': '1px solid #323232',
    'borderBottom': '1px solid #222222',
    'backgroundColor': '#222222',
    'font-family': 'Courier New, monospace',
    'color': 'white',
    'padding': '6px',
    'text-align': 'center',
    'vertical-align': 'center',
    'text-vertical-align': 'center',
    #'fontWeight': 'bold',
    'font-size': '120%',
    'width': '300px'
}



#####################
##### FUNCTIONS #####
#####################

columns = [
    {"id": 0, "name": "pmid"},
    {"id": 1, "name": "article_date"},
    {"id": 2, "name": "abstract"},
    {"id": 3, "name": "keywords"},
    {"id": 4, "name": "bert_answer"},
    {"id": 5, "name": "start_score"},
    {"id": 6, "name": "end_score"},
    {"id": 7, "name": "avg_score"}
]

MIN_YR = 1960
MAX_YR = 2021
MIN_START_DATE = date(2000, 6, 30)
MAX_END_DATE = date(2020, 6, 30)

def upload_search_string(string_dict, search_id, output_bucket, path): ##just uuid and bucket maybe
    output_file = path + '/' + search_id + '.json'
    client = storage.Client.from_service_account_json(credentials_path)
    bucket = client.get_bucket(output_bucket)
    blob = bucket.blob(output_file)
    #file_exists = storage.Blob(bucket=output_bucket, name=output_file).exists(client)
    file_exists = blob.exists(client)

    if not file_exists:
        blob.upload_from_string(string_dict)

    return blob.public_url

pg_connection_string = """dbname='postgres' user='postgres' host='34.xxx.xx.xx' password='xxxxx' sslmode='disable'"""

def run_sql(sql_string):
    conn = psycopg2.connect(pg_connection_string)
    cur = conn.cursor()
    cur.execute(sql_string)
    data = cur.fetchall()
    conn.close()
    return data

def find_keywords(question):
    """Given a question, find keywords and return a list"""
    question = ' '.join(ky.get_clean_words(question))
    print(question)
    #keywords = ky.get_keywords_from_question(question)
    keyword_list = list(ky.get_keywords_from_question(question))
    print('this is keyword_list:')
    print(keyword_list)
    # list of words in question but not in extracted keywords
    # if not in extracted keyword but low freq, we will still include as keyword
    list_words_question = [w for w in question.split() if w not in keyword_list]
    print('this is list_words_question')
    print(list_words_question)
    if len(list_words_question)>0:
        string_wq = """','""".join(list_words_question)
        string_wq = """('""" + string_wq + """')"""
        low_freq_sql =  """
                    SELECT word
                    FROM prod.word_freq
                    WHERE freq::float<0.1
                    and word in {words_in_question}
                    """.format(words_in_question=string_wq)
        print(low_freq_sql)
        data_word = run_sql(low_freq_sql)
        list_low_freq = [i[0] for i in data_word]
    else:
        list_low_freq = []
    print('this is list_low_freq:')
    print(list_low_freq)
    final_keyword_list = list_low_freq
    final_keyword_list.extend(keyword_list)
    print('this is final_keyword_list:')
    print(final_keyword_list)
    return final_keyword_list

def find_candidate_abstracts(final_keyword_list, num_input, start_date, end_date):

    """ Given a keyword_list, find candidate pmids.  Returns dataframe with some metadata and abstract"""

    final_df = pd.DataFrame()
    fetched_pmids = []
    for j in range(1, len(final_keyword_list)+1):
        if len(final_df) > num_input: #We only want a few results
            break
        #########################  ALL THIS HAS TO BE RE WRITTEN FOR POSTGRES TABLES   ##################
        # generate string for filter in the SQL
        sql_list = []
        print('string filter iteration: ' + str(j))
        for i in range(1, len(final_keyword_list)-j+2):
            word = final_keyword_list[i-1]
            table_alias = 'abcdefghijk'
            if i==1:
                current_sql = """(select pmid from prod.words_pmids where word='{word}') a""".format(word= word)
            else:
                current_sql = """ join (select pmid 
                                from prod.words_pmids 
                                where word='{word}') {this_alias} 
                                on {this_alias}.pmid={prev_alias}.pmid""".format(word = word,
                                                                                 this_alias = table_alias[i-1],
                                                                                 prev_alias = table_alias[i-2])
            #string_filter += '''and lower(abstract) like '%{word}%'  '''.format(word = word)
            sql_list.append(current_sql)
        intersect_sql = ' '.join(sql_list)
        intersect_sql = 'select distinct a.pmid from ' + intersect_sql + ' limit 50'
        print(intersect_sql)
        intersect_pmids = run_sql(intersect_sql)
        list_pmids = [i[0] for i in intersect_pmids]
        if len(list_pmids)>0:
            pmid_in_string = """', '""".join(list(set(list_pmids)))
            pmid_in_filter = """and pmid in ('"""+ pmid_in_string + """')"""
            current_keywords = final_keyword_list[0:(len(final_keyword_list)-j+1)]
            keywords_all_string = '+'.join(current_keywords)
            pmid_filter = ''
            if len(fetched_pmids)>0:
                pmid_string = """', '""".join(list(set(fetched_pmids)))
                pmid_filter = """and pmid not in ('"""+ pmid_string + """')"""
            query = """
                    SELECT pmid, article_date, abstract, '{keywords_all}' as keywords
                    FROM prod.abstracts
                    WHERE 1=1  and article_date > '{start_date}' and article_date < '{end_date}'
                    {pmid_in_filter}
                    {pmid_filter}
                    order by article_date desc
                    limit {max_results}
                    """.format(keywords_all = keywords_all_string, pmid_in_filter = pmid_in_filter,
                               max_results = str(num_input), pmid_filter = pmid_filter,
                               start_date = start_date, end_date = end_date)
            ######################## REWRITE above for postgres ##################
            print(query)
            data_pg = run_sql(query)
            if not data_pg:
                continue
            print(data_pg)
            df = pd.DataFrame(data_pg)
            print(df)
            df.columns = ['pmid', 'article_date', 'abstract', 'keywords']
            print(df)
            final_df = final_df.append(df, ignore_index = True)
            fetched_pmids = fetched_pmids + df['pmid'].tolist()
            return final_df

def find_answers(final_df, num_input, question_input, search_uuid, search_ts):
    # find bert answer
    num_rows = min(num_input, len(final_df.index))
    final_df = final_df.head(num_rows) #Will evaluate only top rows of dataframe
    final_df = final_df.reset_index(drop=True)
    final_df['bert_answer'] = ''
    final_df['start_score'] = ''
    final_df['end_score'] = ''
    final_df['avg_score'] = ''
    for i, row in final_df.iterrows():
        url_req = 'http://34.107.125.243:5000/{pmid}/{question}'.format(pmid=row['pmid'], question=question_input)
        print(row['pmid'])
        print(url_req)
        bert_request = requests.get(url_req)
        bert_response = json.loads(bert_request.text.replace('\n',''))
        answer = bert_response['answer'].replace(' ##', '')
        final_df.at[i,'bert_answer'] = answer
        final_df.at[i,'start_score'] = bert_response['start_score']
        final_df.at[i,'end_score'] = bert_response['end_scores']
        final_df.at[i,'avg_score'] = str((float(final_df.at[i,'start_score']) + float(final_df.at[i,'end_score']))/2)
        print(bert_response)
        track_responses(search_ts, search_uuid,row['pmid'], row['keywords'],
                        final_df.at[i, 'bert_answer'], str(bert_response['start_score']),
                        str(bert_response['end_scores']), final_df.at[i,'avg_score'])
    final_df = final_df[final_df['bert_answer'].apply(lambda x: '[CLS]' not in x and '[SEP]' not in x and x!='')]
    print(final_df.head(5))
    final_df = final_df.sort_values('avg_score', ascending=False)
    return final_df

def track_session(question, search_uuid, search_ts):
    """
    One of three functions to track data.  This one is for session information + question asked"""
    user_ip = request.remote_addr
    user_ua = request.headers['User-Agent']
    log_dict = {'user_ip': user_ip,
                'user_ua': user_ua,
                'question': question,
                'search_uuid': str(search_uuid),
                'search_ts': search_ts
                }
    upload_search_string(str(log_dict), search_ts + '-uuid-' + search_uuid, 'mrc_logs', 'search')

def track_responses(search_ts, search_uuid, pmid, keywords, bert_answer,
                    start_score, end_score , avg_score):
    log_results = {'search_uuid': search_uuid,
                   'pmid': pmid,
                   'keywords': keywords,
                   'bert_answer': bert_answer,
                   'start_score': start_score,
                   'end_score': end_score,
                   'avg_score': avg_score
                   }
    upload_search_string(str(log_results), search_ts + '-uuid-' + search_uuid + '-' + pmid, 'mrc_logs', 'results')

def track_duration(start_now, search_uuid, search_ts):
    end_search_ts = time.time()
    search_duration_s =str(round(end_search_ts -start_now))
    print('search duration: ' + search_duration_s)
    search_duration = {'search_uuid': search_uuid,
                       'search_duration': search_duration_s
                       }
    upload_search_string(str(search_duration), search_ts + '-uuid-' + search_uuid, 'mrc_logs', 'duration')

#####################
###### LAYOUT #######
#####################
dash_app.layout = html.Div([

    ###### HIDDEN DIV TO SHARE GLOBAL DATAFRAME
    #html.Div(id='hidden-dff', style={'display': 'none'}),
    #html.Div(id='filtered-dff', style={'display': 'none'}),
    #html.Div(id='hidden-pgn', style={'display': 'none'}),
    #html.Div(id='games_played', style={'display': 'none'}),
    #html.Div(id='intermediate-dff', style={'display': 'none'}),


    ###### TOP TITLE ######
    html.Br(),
    html.Br(),
    html.Div([html.Img(src='data:image/png;base64,{}'.format(encoded_image_1.decode()))],
             style={'display': 'inline-block', 'height': '180px', 'align-items': 'center',
                    'justify-content': 'center', 'display': 'flex'}, id='logo'),
    html.Br(),
    html.Br(),
    ###### TABS  ######
    html.Br(),
    dcc.Tabs(id="tabs", children=[

        ###### FIRST TAB: INPUT USER ######

        dcc.Tab(label='Ask your question', children=[
            html.Div(html.Hr(), style={'marginLeft': 40, 'marginRight':160}),
            html.H5('Using the PUBMED database of all medical/biotech research in history, you can ask a question',
                            style={'font-family': 'Courier New, monospace', 'marginLeft': 40}),
            html.H5('and receive high quality answers with cutting edge BERT natural language processing.',
                            style={'font-family': 'Courier New, monospace', 'marginLeft': 40}),
            html.Div(html.Hr(), style={'marginLeft': 40, 'marginRight':160}),
            html.H5(
                'Input your question here:'
                , style={'font-family': 'Courier New, monospace', 'marginLeft': 40}),
            html.Div(dcc.Input(id="question", type="text", placeholder="",
                               style={'marginLeft': 40, 'backgroundColor': '#222222', 'color': '#ffffff',
                                      'height': '40px', 'width': '40%', 'border': '1px solid #c0c0c0', 'borderRadius': '3px'})),
            html.Br(),
            # Date range Picker
            html.H5(
                'Choose article publication date range:'
                , style={'font-family': 'Courier New, monospace', 'marginLeft': 40}),
            html.Div(
                [
                    html.H3(id="output-container"),
                    html.Div(
                        [
                            dcc.RangeSlider(
                                id="date_slider",
                                min=MIN_YR,
                                max=MAX_YR,
                                count=1,
                                step=1,
                                value=[MIN_YR, MAX_YR],
                                marks={yr: yr for yr in range(10*math.floor(MIN_YR/10), MAX_YR+1,10)},
                            )
                        ],
                        style={"width": "40%",'marginLeft': 40},
                    ),
                    html.Br(),
                    html.Div(
                        [
                            dcc.DatePickerSingle(
                                id="start_range",
                                min_date_allowed=MIN_START_DATE,
                                max_date_allowed=MAX_END_DATE,
                                initial_visible_month=MIN_START_DATE,
                                display_format="MMM D, YYYY",
                                date=MIN_START_DATE,
                            ),
                            dcc.DatePickerSingle(
                                id="end_range",
                                min_date_allowed=MIN_START_DATE,
                                max_date_allowed=MAX_END_DATE,
                                initial_visible_month=MAX_END_DATE,
                                date=MAX_END_DATE,
                                display_format="MMM D, YYYY",
                            ),
                        ],
                        style={"width": "40%",'marginLeft': 100}
                    ),
                ]
            )
        ,
        # End of date range picker
        html.Br(),
        html.H5('How many of the top articles do you want to evaluate? (1.5 seconds each):',
                style={'font-family': 'Courier New, monospace', 'marginLeft': 40}),
        html.Br(),
        html.Div(
            dcc.Dropdown(
                id='num-abstracts', #'backgroundColor': '#222222', 'color': '#ffffff',
                #'height': '40px', 'border': '1px solid #c0c0c0', 'borderRadius': '3px'},
                options=[
                    {'label': '5', 'value': '5'},
                    {'label': '10', 'value': '10'}
                ],
                value='5'
            ), style={'marginLeft': 40, 'width':'5%'}
        ),
        html.Div(html.Hr(), style={'marginLeft': 40, 'marginRight':160}),
        html.H5(
            'Press the button to fetch your data. It can take a few seconds.'
            , style={'font-family': 'Courier New, monospace', 'marginLeft': 40}),
        html.Br(),
        dbc.Button('Fetch data!', id='fetch-data-button', n_clicks=0, className="btn btn-warning",
                   style={'display': 'inline-block', 'marginLeft': 40}),
        dcc.Loading(id="loading-1", children=[html.Div(id="loading-output-1")], type="default",
                    style={'display': 'inline-block', 'marginLeft': 60}),
        html.Br(),
        html.Div(html.Hr(), style={'marginLeft': 40, 'marginRight':160}),
        html.H5(
            'Your BERT answer:'
            , style={'font-family': 'Courier New, monospace', 'marginLeft': 40}),
        html.Br(),
        html.Br(),
        #html.Div(id='bert-answer', style={'font-family': 'Courier New, monospace', 'marginLeft': 200}),
        dash_table.DataTable(
            style_data={'whiteSpace': 'normal', 'height': 'auto'},
            style_header={'backgroundColor': 'rgb(30, 30, 30)'},
            style_cell={'backgroundColor': 'rgb(50, 50, 50)', 'color': 'white'},
            id='table_df',
            page_size=5,
            data=[]
        ),
        html.Br(),
        html.Br(),
        html.Br(),
        html.Br()
            ],style=tab_style,
                    selected_style=tab_selected_style),

        # The  &nbsp; are to make empty lines
        dcc.Tab(label='About this site',
                children=[html.Div([
                    html.Br(),
                    html.Br(),
                    dcc.Markdown('''
                                Created and maintained by Biotech MRC.
                              
                                
                                &nbsp;  
                                &nbsp;
                                &nbsp;  
                                &nbsp;      
                                
                                
                                ''')
                ]
                )], style=tab_style, selected_style=tab_selected_style)
    ], style=tabs_styles)
])




#####################
###### CALLBACKS ####
#####################

@dash_app.callback(
    [Output("start_range", "date"), Output("end_range", "date")],
    [Input("date_slider", "value")],
    [State("start_range", "date"), State("end_range", "date")],
)
def update_date_range(slider_dates, date_range_start, date_range_end):
    start_yr, end_yr = slider_dates[0], slider_dates[1]

    if date_range_start is not None:
        date_range_start = str(start_yr) + date_range_start[4:]

    if date_range_end is not None:
        date_range_end = str(end_yr) + date_range_end[4:]

    return date_range_start, date_range_end





@dash_app.callback([Output("table_df", "data"), Output('table_df', 'columns'), Output('loading-output-1', 'children')],
                   [Input('fetch-data-button', 'n_clicks')],
                   [State('num-abstracts', 'value'), State('question', 'value'),
                    State("start_range", "date"), State("end_range", "date")])
def output_table(n_clicks, num_input, question_input, start_date, end_date):
    print('question input:')
    print(question_input)
    num_input = int(num_input)
    question = question_input.replace(' ', '+')
    search_uuid = str(uuid.uuid1())
    start_now = time.time()
    now = dt.now()
    search_ts = now.strftime("%Y-%m-%d %H:%M:%S")
    # Send session tracking data to GCS
    track_session(question, search_uuid, search_ts)
    # Find keywords from question
    final_keyword_list = find_keywords(question)
    # Find candidate pmids, and get a dataframe we will use to display results
    final_df = find_candidate_abstracts(final_keyword_list, num_input, start_date, end_date)
    final_df = find_answers(final_df, num_input, question_input, search_uuid, search_ts)
    # Send duration tracking to GCS
    track_duration(start_now, search_uuid, search_ts)

    return final_df.values, columns,  ' '


if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=80)